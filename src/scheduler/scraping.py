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
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlmodel import select

from db.session import async_session
from llm import get_provider as llm_get_provider
from llm.base import LLMProviderError
from models import JobScrapeStatus, JobSource, Profile, Settings
from scraper.crawl4ai_client import Crawl4AIClient
from scraper.proxy import resolve_proxy_config, safe_proxy_host
from scraper.rate_limit import resolve_rate_limit
from scraper.redaction import safe_exc
from scraper.sites import scrapers as scraper_registry
from scraper.types import ScrapeQuery
from services import env_secrets
from services.notify import notify_admin_error
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

# Floor applied to manual Run-now verification runs so a bounded 10-listing
# check completes in minutes, not hours. Cron runs keep the per-source
# sustained budget untouched.
_MANUAL_RUN_MIN_RPM = 6.0

# Plan 64 § D.6 — emit the LinkedIn-without-proxy warning ONCE per process to
# avoid drowning per-firing logs. The flag flips True on first observation;
# subsequent firings stay silent.
_LINKEDIN_PROXY_WARNED: bool = False


# ── Helpers ──────────────────────────────────────────────────────────────


# Cap the per-firing fan-out for keyword sources: one ScrapeQuery per target
# title, at most this many titles per firing. Titles beyond the cap are NOT
# starved — `_rotation_offset` slides the window across firings so every
# title (and every target city) gets queried over a day.
_MAX_TITLE_QUERIES = 3

# Per-title listing budget for CRON firings (manual Run-now keeps its own
# bounded budget). 3 titles × 60 ≈ 180 fresh listings per firing ceiling —
# the "moderate" volume profile; with the known-ID skip, steady-state runs
# spend far less than the ceiling.
_CRON_MAX_LISTINGS_PER_QUERY = 60


def _rotation_offset(slots: int, *, period_minutes: int = 30) -> int:
    """Stateless rotation index — advances one step per cron period.

    Time-derived instead of DB-persisted: survives restarts, needs no
    migration, and two processes compute the same window.
    """
    if slots <= 1:
        return 0
    now = datetime.now(UTC)
    step = (now.hour * 60 + now.minute) // max(period_minutes, 1)
    return step % slots


def _compose_queries(
    source: JobSource, settings: Settings, profile: Profile | None
) -> list[ScrapeQuery]:
    """Build the per-source ScrapeQuery list.

    Keyword sources (LinkedIn / Indeed) derive from profile-level
    job-search preferences — ONE query per target title so multi-title
    users get OR semantics across searches (docs/design/
    JOB_SEARCH_PREFERENCES.md § E). A non-empty per-source Settings
    keyword override wins and behaves like the legacy single query.
    Company-list sources are unchanged.
    """
    from config import settings as app_settings
    from services.search_prefs import derive_source_inputs

    if source is JobSource.WORKDAY:
        return [ScrapeQuery(company_filter=list(settings.workday_companies or []))]
    if source is JobSource.GREENHOUSE:
        return [ScrapeQuery(company_filter=list(app_settings.greenhouse_companies or []))]
    if source is JobSource.LEVER:
        return [ScrapeQuery(company_filter=list(app_settings.lever_companies or []))]
    if source is JobSource.ASHBY:
        return [ScrapeQuery(company_filter=list(app_settings.ashby_companies or []))]
    if source in (JobSource.LINKEDIN, JobSource.INDEED):
        keywords, location, is_override = derive_source_inputs(profile, settings, source)
        if is_override:
            # Legacy behavior: the override keyword list is ONE query.
            return [ScrapeQuery(keywords=keywords, location=location)]

        # Rotate the title window so titles beyond _MAX_TITLE_QUERIES get
        # their turn on later firings instead of never running.
        titles = list(keywords)
        if len(titles) > _MAX_TITLE_QUERIES:
            off = _rotation_offset(len(titles))
            titles = [titles[(off + i) % len(titles)] for i in range(_MAX_TITLE_QUERIES)]
            log.info(
                "scraping.%s user=%s: %d target titles, this firing queries %s",
                source.value,
                settings.user_id,
                len(keywords),
                titles,
            )

        # Rotate target cities the same way — the old behavior pinned every
        # scrape to the FIRST city forever.
        cities = [c for c in (getattr(profile, "target_cities", None) or []) if c.strip()]
        if len(cities) > 1:
            location = cities[_rotation_offset(len(cities))]

        return [
            ScrapeQuery(
                keywords=[title],
                location=location,
                max_listings=_CRON_MAX_LISTINGS_PER_QUERY,
                raw_meta={"target_title": title},
            )
            for title in titles
        ]
    return [ScrapeQuery()]


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


async def _scrape_one_user(
    session, *, settings: Settings, source: JobSource, max_listings: int | None = None
) -> None:
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

    profile = (
        await session.exec(select(Profile).where(Profile.user_id == settings.user_id))
    ).one_or_none()

    # Skip unconfigured sources instead of firing a meaningless query
    # (empty keywords / empty company list ⇒ "SUCCESS · 0 listings" noise,
    # which reads as a working scrape that found nothing). The Settings ·
    # Sources panel surfaces the not-configured state; the manual Run-now
    # endpoint rejects unconfigured sources loudly before queueing.
    if not env_secrets.scraper_source_configured(source, settings, profile):
        log.debug(
            "scraping.%s skipped for user=%s: source not configured",
            source.value,
            settings.user_id,
        )
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
    if max_listings is not None and rl_config.rpm < _MANUAL_RUN_MIN_RPM:
        # Manual Run-now is a small bounded verification run; the sustained
        # 24/7 crawl budget (e.g. LinkedIn 0.4 rpm) would stretch a 10-listing
        # run past an hour. One short burst at 6 rpm is within the operator-
        # tunable range and doesn't move the sustained crawl posture.
        rl_config = rl_config.model_copy(
            update={"rpm": _MANUAL_RUN_MIN_RPM, "delay_lo": 2.0, "delay_hi": 5.0}
        )
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

    queries = _compose_queries(source, settings, profile)
    if max_listings is not None:
        # Manual Run-now is a bounded verification run — split the listing
        # budget across the per-title queries instead of multiplying it.
        per_query = max(1, max_listings // len(queries))
        queries = [q.model_copy(update={"max_listings": per_query}) for q in queries]
    statuses: list[JobScrapeStatus] = []
    try:
        for query in queries:
            run = await run_scraper(
                session,
                scraper=scraper,
                user_id=settings.user_id,
                query=query,
                triggered_by="cron" if max_listings is None else "manual",
            )
            statuses.append(run.status)
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

    # Counter semantics across the per-title query fan-out: any healthy run
    # resets (the source works); all-FAILED increments once per firing.
    if any(s in (JobScrapeStatus.SUCCESS, JobScrapeStatus.PARTIAL) for s in statuses):
        if previous_failures != 0:
            counters[source.value] = 0
            settings.consecutive_scrape_failures = counters
            session.add(settings)
    elif JobScrapeStatus.FAILED in statuses:
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


async def _scrape_source(
    source: JobSource,
    *,
    max_listings: int | None = None,
    only_user_id: int | None = None,
) -> None:
    """Job body for `scraping.<source>`. One firing → iterate enabled users.

    `max_listings` / `only_user_id` are set only by manual "Run now"
    triggers (Settings · Sources): a bounded run scoped to the requesting
    user so the operator gets fast, attributable feedback instead of a
    multi-hour all-user crawl at production rate limits.
    """
    async with async_session() as session:
        rows = (await session.exec(select(Settings))).all()
        for s in rows:
            if only_user_id is not None and s.user_id != only_user_id:
                continue
            await _scrape_one_user(session, settings=s, source=source, max_listings=max_listings)
        await session.commit()


# ── Per-source job entrypoints (named so APScheduler can serialize them) ─


async def scrape_linkedin(max_listings: int | None = None, only_user_id: int | None = None) -> None:
    await _scrape_source(JobSource.LINKEDIN, max_listings=max_listings, only_user_id=only_user_id)


async def scrape_workday(max_listings: int | None = None, only_user_id: int | None = None) -> None:
    await _scrape_source(JobSource.WORKDAY, max_listings=max_listings, only_user_id=only_user_id)


async def scrape_greenhouse(
    max_listings: int | None = None, only_user_id: int | None = None
) -> None:
    await _scrape_source(JobSource.GREENHOUSE, max_listings=max_listings, only_user_id=only_user_id)


async def scrape_lever(max_listings: int | None = None, only_user_id: int | None = None) -> None:
    await _scrape_source(JobSource.LEVER, max_listings=max_listings, only_user_id=only_user_id)


async def scrape_ashby(max_listings: int | None = None, only_user_id: int | None = None) -> None:
    await _scrape_source(JobSource.ASHBY, max_listings=max_listings, only_user_id=only_user_id)


async def scrape_indeed(max_listings: int | None = None, only_user_id: int | None = None) -> None:
    await _scrape_source(JobSource.INDEED, max_listings=max_listings, only_user_id=only_user_id)


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
