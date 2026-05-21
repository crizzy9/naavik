"""Phase 2 scraping crons — one job per JobSource in scraper.sites:scrapers.

Per docs/plans/35-0.2.0.10-apscheduler.md § D (graduating to
docs/design/SCHEDULER.md on archive). Each cron iterates Settings rows for
users who have not disabled the source, resolves their LLM provider for AI
enrichment, composes a ScrapeQuery per source, invokes
scraper_service.run_scraper, and lets the per-listing tier-1 + scraper-fatal
tier-2 error handling persist results into JobScrapeRun.

Consecutive-failure counter (§ D.5): per-source counter persisted on
Settings.consecutive_scrape_failures (JSON dict). Cron always runs the
scrape; on FAILED the counter increments and SUCCESS / PARTIAL resets to 0.
A single Discord admin alert fires when the counter transitions 2 → 3
(threshold-cross) and stays silent until the next SUCCESS / PARTIAL clears
the counter. Auto-resume on first SUCCESS — no deadlock, no notification
storm.

Indeed uses IntervalTrigger(minutes=90) — cron does not support 90-min steps
(§ D.6 + § Risk row). All other sources use CronTrigger with the
BACKEND.md § I.1 defaults.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlmodel import select

from db.session import async_session
from llm import get_provider as llm_get_provider
from llm.base import LLMProviderError
from models import JobScrapeStatus, JobSource, Settings
from scraper.crawl4ai_client import Crawl4AIClient
from scraper.proxy import resolve_proxy_config, safe_proxy_host
from scraper.rate_limit import resolve_rate_limit
from scraper.redaction import safe_exc
from scraper.sites import scrapers as scraper_registry
from scraper.types import ScrapeQuery
from services.notifications import notify_admin_error
from services.scraper_service import run_scraper

log = logging.getLogger(__name__)


# Per-source cron defaults sourced from BACKEND.md § I.1. Treated as the
# "operator left Settings.source_schedules empty" fallback. Indeed is absent
# here — see _INDEED_INTERVAL_MINUTES; cron does not support 90-min steps.
_DEFAULT_CRON_SCHEDULES: dict[str, str] = {
    JobSource.LINKEDIN.value: "*/30 * * * *",
    JobSource.WORKDAY.value: "0 * * * *",
    JobSource.GREENHOUSE.value: "0 * * * *",
    JobSource.LEVER.value: "0 * * * *",
    JobSource.ASHBY.value: "0 * * * *",
}

_INDEED_INTERVAL_MINUTES = 90

_CONSECUTIVE_FAIL_THRESHOLD = 3

# Plan 64 § D.6 — emit the LinkedIn-without-proxy warning ONCE per process to
# avoid drowning per-firing logs. The flag flips True on first observation;
# subsequent firings stay silent.
_LINKEDIN_PROXY_WARNED: bool = False


# ── Helpers ──────────────────────────────────────────────────────────────


def _compose_query(source: JobSource, settings: Settings) -> ScrapeQuery:
    """Build a per-source ScrapeQuery from Settings + env-loaded config."""
    from config import settings as app_settings

    if source is JobSource.WORKDAY:
        return ScrapeQuery(company_filter=list(settings.workday_companies or []))
    if source is JobSource.GREENHOUSE:
        return ScrapeQuery(company_filter=list(app_settings.greenhouse_companies or []))
    if source is JobSource.LEVER:
        return ScrapeQuery(company_filter=list(app_settings.lever_companies or []))
    if source is JobSource.ASHBY:
        return ScrapeQuery(company_filter=list(app_settings.ashby_companies or []))
    if source is JobSource.LINKEDIN:
        return ScrapeQuery(
            keywords=list(settings.linkedin_keywords or []),
            location=settings.linkedin_location,
        )
    if source is JobSource.INDEED:
        return ScrapeQuery(
            keywords=list(settings.indeed_keywords or []),
            location=settings.indeed_location,
        )
    return ScrapeQuery()


async def _maybe_notify_threshold_cross(
    *,
    settings: Settings,
    source: JobSource,
    previous_failures: int,
    new_failures: int,
) -> None:
    # Fire iff the counter just crossed _CONSECUTIVE_FAIL_THRESHOLD on this
    # firing. Past-threshold failures stay silent until a SUCCESS / PARTIAL
    # resets the counter — re-arming the alert for the next bad run.
    if previous_failures >= _CONSECUTIVE_FAIL_THRESHOLD:
        return
    if new_failures < _CONSECUTIVE_FAIL_THRESHOLD:
        return
    log.info(
        "scraping.%s for user=%s crossed consecutive-FAIL threshold %d",
        source.value,
        settings.user_id,
        _CONSECUTIVE_FAIL_THRESHOLD,
    )
    await notify_admin_error(
        settings=settings,
        message=(
            f"Scraping for {source.value} has failed "
            f"{new_failures}x consecutively. Cron continues to run "
            f"on schedule; counter clears on first SUCCESS / PARTIAL."
        ),
    )


async def _scrape_one_user(session, *, settings: Settings, source: JobSource) -> None:
    """Run one (user, source) scrape; mutate Settings.consecutive_scrape_failures.

    Skips only when `sources_enabled[source.value] is False` — operator
    explicitly disabled. The consecutive-FAIL counter NEVER causes a skip;
    the scrape always fires so the counter can recover. SUCCESS / PARTIAL
    resets to 0. FAILED increments by 1. TIMED_OUT and other top-level
    exceptions surface here as raised exceptions and also increment.

    The Discord admin alert fires exactly ONCE, on the firing where the
    counter transitions from `_CONSECUTIVE_FAIL_THRESHOLD - 1` →
    `_CONSECUTIVE_FAIL_THRESHOLD` (e.g. 2 → 3). Subsequent failures stay
    silent; first SUCCESS / PARTIAL clears the counter so the next
    threshold-cross will alert again.
    """
    if settings.sources_enabled.get(source.value, True) is False:
        return

    counters: dict[str, int] = dict(settings.consecutive_scrape_failures or {})
    previous_failures = int(counters.get(source.value, 0))

    try:
        provider = llm_get_provider(settings)
    except LLMProviderError as exc:
        log.warning(
            "LLM provider unavailable user=%s source=%s: %s",
            settings.user_id,
            source.value,
            exc,
        )
        provider = None

    scraper_cls = scraper_registry[source.value]
    # Plan 38 § D.1: operator overrides in Settings.scraper_rate_limits win
    # over class-attr defaults. resolve_rate_limit returns the class-attr
    # fallback when no operator override exists or when the override fails
    # validation.
    rl_config = resolve_rate_limit(settings, source)
    # Plan 64 § D — proxy resolution. LinkedIn-only this plan; non-LinkedIn
    # sources always get None back. Boot-time validation in `config.py`
    # already caught a malformed env-var; resolver returning None for
    # LinkedIn means env-var unset (warn once, continue per § D.6 "fail loud
    # iff configured BUT broken" — unset is a different failure mode).
    proxy_config = resolve_proxy_config(source)
    global _LINKEDIN_PROXY_WARNED
    if source is JobSource.LINKEDIN and proxy_config is None and not _LINKEDIN_PROXY_WARNED:
        log.warning(
            "LINKEDIN_PROXY_URL not set; LinkedIn scrapes will use direct "
            "connection — proxy strongly recommended for production deployments"
        )
        _LINKEDIN_PROXY_WARNED = True
    client = Crawl4AIClient(
        rate_limit_per_minute=rl_config.rpm,
        random_delay_seconds=(rl_config.delay_lo, rl_config.delay_hi),
        use_undetected_adapter=scraper_cls.use_undetected_adapter,
        proxy_config=proxy_config,
    )
    if proxy_config is not None:
        log.info(
            "scraping.%s for user=%s routing through proxy=%s",
            source.value,
            settings.user_id,
            safe_proxy_host(proxy_config.url),
        )
    scraper = scraper_cls(
        client=client,
        session=session,
        user_id=settings.user_id,
        provider=provider,
    )

    try:
        run = await run_scraper(
            session,
            scraper=scraper,
            user_id=settings.user_id,
            query=_compose_query(source, settings),
            triggered_by="cron",
        )
    except Exception as exc:  # noqa: BLE001 — per-user isolation
        # Plan 64 PR #165 delta-fix HIGH-1 + HIGH-2: `log.exception` would
        # attach the full traceback (which embeds `repr(exc)` for every
        # chained level); upstream libraries like httpx / Playwright /
        # crawl4ai routinely embed the credentialed proxy URL in their
        # exception messages. Switch to `log.error` + `safe_exc` so the
        # chain is URL-stripped before reaching the log handler. Trade-off:
        # we lose the stack trace; we gain guaranteed credential redaction.
        # Telemetry surfaces (JobScrapeRun.errors, raw_meta) carry the
        # safe form too; full traceback is recoverable via debugger if a
        # repro is needed.
        redacted = safe_exc(exc)
        log.error(
            "scraping.%s failed for user=%s: %s",
            source.value,
            settings.user_id,
            redacted,
        )
        counters[source.value] = previous_failures + 1
        settings.consecutive_scrape_failures = counters
        session.add(settings)
        # Tier-1 admin signal for top-level catastrophes (CancelledError,
        # DB connect failures) — these never produced a JobScrapeRun row,
        # so the operator has no other path to learn this happened. The
        # `redacted` form goes into the Discord webhook body too; raw
        # `str(exc)` would leak creds via the chain.
        await notify_admin_error(
            settings=settings,
            message=(
                f"scraping.{source.value} cron raised at top level "
                f"for user={settings.user_id}: {redacted}"
            ),
        )
        return

    if run.status in (JobScrapeStatus.SUCCESS, JobScrapeStatus.PARTIAL):
        if previous_failures != 0:
            counters[source.value] = 0
            settings.consecutive_scrape_failures = counters
            session.add(settings)
    elif run.status is JobScrapeStatus.FAILED:
        new_failures = previous_failures + 1
        counters[source.value] = new_failures
        settings.consecutive_scrape_failures = counters
        session.add(settings)
        await _maybe_notify_threshold_cross(
            settings=settings,
            source=source,
            previous_failures=previous_failures,
            new_failures=new_failures,
        )


async def _scrape_source(source: JobSource) -> None:
    """Job body for `scraping.<source>`. One firing → iterate enabled users."""
    async with async_session() as session:
        rows = (await session.exec(select(Settings))).all()
        for s in rows:
            await _scrape_one_user(session, settings=s, source=source)
        await session.commit()


# ── Per-source job entrypoints (named so APScheduler can serialize them) ─


async def scrape_linkedin() -> None:
    await _scrape_source(JobSource.LINKEDIN)


async def scrape_workday() -> None:
    await _scrape_source(JobSource.WORKDAY)


async def scrape_greenhouse() -> None:
    await _scrape_source(JobSource.GREENHOUSE)


async def scrape_lever() -> None:
    await _scrape_source(JobSource.LEVER)


async def scrape_ashby() -> None:
    await _scrape_source(JobSource.ASHBY)


async def scrape_indeed() -> None:
    await _scrape_source(JobSource.INDEED)


_JOB_FUNCS = {
    JobSource.LINKEDIN.value: scrape_linkedin,
    JobSource.WORKDAY.value: scrape_workday,
    JobSource.GREENHOUSE.value: scrape_greenhouse,
    JobSource.LEVER.value: scrape_lever,
    JobSource.ASHBY.value: scrape_ashby,
    JobSource.INDEED.value: scrape_indeed,
}


# ── Registration ────────────────────────────────────────────────────────


def register_scraping_jobs(scheduler: AsyncIOScheduler) -> None:
    """Register one cron per JobSource present in scraper.sites:scrapers.

    Indeed uses IntervalTrigger(minutes=90) because cron does not support
    90-min steps. All other sources use CronTrigger with the BACKEND.md
    § I.1 defaults. All registrations carry `jitter=30` to smear the
    minute-boundary burst.
    """
    for source_value in scraper_registry:
        job_func = _JOB_FUNCS[source_value]
        if source_value == JobSource.INDEED.value:
            trigger = IntervalTrigger(minutes=_INDEED_INTERVAL_MINUTES, jitter=30)
        else:
            trigger = CronTrigger.from_crontab(
                _DEFAULT_CRON_SCHEDULES[source_value],
                timezone="UTC",
            )
            trigger.jitter = 30
        scheduler.add_job(
            job_func,
            trigger,
            id=f"scraping.{source_value}",
            name=f"scraping.{source_value}",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300,
        )


__all__ = [
    "register_scraping_jobs",
    "scrape_ashby",
    "scrape_greenhouse",
    "scrape_indeed",
    "scrape_lever",
    "scrape_linkedin",
    "scrape_workday",
]
