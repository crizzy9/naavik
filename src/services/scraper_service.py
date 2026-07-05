"""Scraper invocation orchestrator — opens a JobScrapeRun, streams RawJobs
through `job_service.upsert_job`, finalizes the run with counters + errors.

Per docs/design/SCRAPER_BASE.md § F (graduated from plan 29 § D.10).
Lifecycle:

1. Open `JobScrapeRun` row at status=RUNNING.
2. Iterate `scraper.scrape(query) -> AsyncIterator[RawJob]`. Per-yield: call
   `job_service.upsert_job(...)`. Track new/updated counters. Per-listing
   exceptions append to `errors[]` and continue (recoverable tier).
3. On scraper-fatal exception: status=FAILED (no jobs yielded) or PARTIAL
   (some jobs yielded). On `asyncio.CancelledError`: status=TIMED_OUT, then
   re-raise so the scheduler can react.
4. `finally`: update the same JobScrapeRun row in-place with final counters
   + status + duration_ms.

`run_scraper` returns the JobScrapeRun for caller observability. Caller is
responsible for `session.commit()` at its boundary — service writes
`session.flush()` only.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import JobScrapeRun, JobScrapeStatus, Settings
from scraper.base import ScraperBase
from scraper.redaction import safe_exc, safe_url
from scraper.types import ScrapeQuery
from services import job_service
from services.notify import notify_scrape_run_summary

log = logging.getLogger(__name__)


async def run_scraper(
    session: AsyncSession,
    *,
    scraper: ScraperBase,
    user_id: int,
    query: ScrapeQuery | None = None,
    triggered_by: str = "manual",
    notify: bool = True,
) -> JobScrapeRun:
    """Run one scraper invocation; persist Jobs + JobScrapeRun row.

    Per `JOB_MODEL.md § F.4`, `record_scrape_run` is the helper that writes
    the table; this function orchestrates the lifecycle around it.
    """
    if query is None:
        query = ScrapeQuery()

    started_at = datetime.now(UTC)
    run = await job_service.record_scrape_run(
        session,
        user_id=user_id,
        source=scraper.source,
        status=JobScrapeStatus.RUNNING,
        triggered_by=triggered_by,
        started_at=started_at,
        raw_meta={"scraper_name": scraper.name, "query": query.model_dump()},
    )

    listings_returned = 0
    new_jobs = 0
    updated_jobs = 0
    errors: list[str] = []
    status = JobScrapeStatus.SUCCESS

    # 2026-07 volume rework: seed the scraper with this user's existing
    # external_ids so aggregator scrapers skip the per-listing detail fetch
    # for jobs already in the library — the request budget goes to genuinely
    # NEW postings. Trade-off: existing rows stop getting re-scrape refreshes
    # (postings rarely change; JD enrichment owns description quality now).
    try:
        known = await job_service.list_external_ids(session, user_id=user_id, source=scraper.source)
        scraper.set_known_external_ids(known)
    except Exception:  # noqa: BLE001 — dedup seed is an optimization only
        log.exception("known-id seed failed for %s; scraping without skip", scraper.name)

    try:
        async for raw_job in scraper.scrape(query):
            listings_returned += 1
            try:
                _job, created = await job_service.upsert_job(
                    session,
                    user_id=user_id,
                    source=raw_job.source,
                    external_id=raw_job.external_id,
                    raw=raw_job.to_upsert_payload(),
                    scrape_run_id=run.id,
                )
                if created:
                    new_jobs += 1
                else:
                    updated_jobs += 1
            except Exception as exc:  # noqa: BLE001 — per-listing tolerance
                errors.append(
                    f"stage=upsert url={safe_url(raw_job.source_url)} "
                    f"kind=upsert_failure msg={safe_exc(exc)}"
                )
                log.exception("upsert_job failed for %s", raw_job.source_url)

        # Inherit per-scraper errors collected during scrape() iteration.
        errors.extend(getattr(scraper, "_errors", []))

        if errors and listings_returned > 0:
            status = JobScrapeStatus.PARTIAL
        elif errors and listings_returned == 0:
            status = JobScrapeStatus.FAILED
        else:
            status = JobScrapeStatus.SUCCESS

    except asyncio.CancelledError:
        status = JobScrapeStatus.TIMED_OUT
        errors.append("stage=invocation kind=cancelled msg=asyncio.CancelledError")
        raise
    except Exception as exc:  # noqa: BLE001 — top-level scraper failure
        status = JobScrapeStatus.PARTIAL if listings_returned > 0 else JobScrapeStatus.FAILED
        errors.append(f"stage=invocation kind=fatal msg={safe_exc(exc)}")
        log.exception("scraper %s failed", scraper.name)
    finally:
        finished_at = datetime.now(UTC)
        run.status = status
        run.finished_at = finished_at
        run.listings_returned = listings_returned
        run.new_jobs = new_jobs
        run.updated_jobs = updated_jobs
        run.duplicates_skipped = int(getattr(scraper, "_skipped_known", 0))
        run.errors = errors
        run.duration_ms = int((finished_at - started_at).total_seconds() * 1000)
        # Plan 38 § D.7: per-scrape RL + adapter telemetry into raw_meta.
        # Preserves existing raw_meta keys (scraper_name, query) set by
        # record_scrape_run; getattr() guards against scrapers that don't
        # use Crawl4AIClient (e.g. SampleScraper with stubbed client).
        client = getattr(scraper, "_client", None)
        adapter_used = "undetected" if scraper.use_undetected_adapter else "stealth"
        rl_meta = {
            "hits": getattr(client, "rate_limit_hits", 0),
            "backoff_total_s": float(getattr(client, "backoff_total_s", 0.0)),
            "ua": getattr(client, "user_agent", None),
        }
        existing_meta = dict(run.raw_meta or {})
        existing_meta["rate_limit"] = rl_meta
        existing_meta["adapter_used"] = adapter_used
        # Plan 64 § D.9 — proxy telemetry sub-key. `used: False` when client
        # doesn't have a proxy or doesn't expose the attribute (test fixtures
        # using a SimpleNamespace stub). `host` is the redacted host:port
        # (NEVER userinfo) so creds never reach JSONB. `bytes_estimated` is
        # an upper bound (response HTML length, not socket bytes).
        proxy_obj = getattr(client, "proxy_config", None) if client is not None else None
        if proxy_obj is not None:
            from scraper.proxy import safe_proxy_host

            proxy_meta: dict[str, object] = {
                "used": True,
                "host": safe_proxy_host(proxy_obj.url),
                "provider_hint": proxy_obj.provider_hint,
                "request_count": int(getattr(client, "proxy_request_count", 0)),
                "bytes_estimated": int(getattr(client, "proxy_bytes_estimated", 0)),
            }
        else:
            proxy_meta = {
                "used": False,
                "host": None,
                "provider_hint": None,
                "request_count": 0,
                "bytes_estimated": 0,
            }
        existing_meta["proxy"] = proxy_meta
        run.raw_meta = existing_meta
        session.add(run)
        await session.flush()

    # Per-scrape-run summary notification (plan 37 / 0.2.0.12 § D.1).
    # Score-blind for the 0.2.x window — fires on every SUCCESS / PARTIAL run
    # with new_jobs > 0. Best-effort: any notify-side failure is logged and
    # swallowed so a misbehaving webhook never blocks the cron lifecycle.
    if (
        notify
        and run.new_jobs > 0
        and run.status in (JobScrapeStatus.SUCCESS, JobScrapeStatus.PARTIAL)
    ):
        try:
            user_settings = (
                await session.exec(select(Settings).where(Settings.user_id == user_id))
            ).one_or_none()
            if user_settings is not None:
                top_jobs = await job_service.list_new_jobs_from_run(session, run_id=run.id, limit=5)
                await notify_scrape_run_summary(settings=user_settings, run=run, top_jobs=top_jobs)
        except Exception as exc:  # noqa: BLE001 — notify is best-effort
            log.warning("scrape-run notify failed for run=%s: %s", run.id, exc)

    return run
