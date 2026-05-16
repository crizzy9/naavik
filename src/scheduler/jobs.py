"""APScheduler job registration — Wave 6 crons.

Per BACKEND.md § I.1 + plan 10 § C.7. Phase 1 wires only what Wave 6 needs:

- `applications.auto_apply` — every 5min — process the auto-apply queue
- `admin.aggregate_costs` — daily 00:30 — aggregate `ApiUsage` rows
- `admin.cleanup_stale_docs` — weekly Sun 03:00 — sweep stale GeneratedDocuments
- `admin.daily_db_snapshot` — daily 02:00 — pg_dump-style snapshot
- `admin.refresh_oauth_tokens` — every 6h — skeleton only (Phase 4 lights up)

Phase 2-5 jobs (scraping, email sync, outreach) attach in their plans.
Job functions take no arguments; they create their own DB session inside
to avoid sharing async sessions across the scheduler thread boundary.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlmodel import select

from db.session import async_session
from models import ApiUsage

log = logging.getLogger(__name__)


# ── Job bodies ────────────────────────────────────────────────────────


async def auto_apply() -> None:
    """`applications.auto_apply` — every 5min."""
    from services.application_service import process_auto_apply_queue
    from services.notifications import notify_application_submitted

    async with async_session() as session:
        from sqlmodel import select as _select

        from models import Application, Settings

        async def _notify(application: Application):
            settings = (
                await session.exec(_select(Settings).where(Settings.user_id == application.user_id))
            ).one_or_none()
            if settings is None:
                return
            await notify_application_submitted(settings=settings, application=application)

        result = await process_auto_apply_queue(session, notify_fn=_notify)
        await session.commit()
    log.info(
        "auto_apply cron processed=%d submitted=%d failed=%d skipped_by_cap=%d",
        result.processed,
        result.submitted,
        result.failed,
        result.skipped_by_cap,
    )


async def aggregate_costs() -> None:
    """`admin.aggregate_costs` — daily 00:30. Logs summary; tables are read by UI."""
    async with async_session() as session:
        # Just log a summary line per provider for the previous 24h.
        from sqlalchemy import func

        threshold = datetime.now(UTC) - timedelta(days=1)
        stmt = (
            select(
                ApiUsage.provider,
                func.count(ApiUsage.id),
                func.coalesce(func.sum(ApiUsage.cost_usd), 0.0),
                func.coalesce(func.sum(ApiUsage.input_tokens), 0),
                func.coalesce(func.sum(ApiUsage.output_tokens), 0),
            )
            .where(ApiUsage.occurred_at >= threshold)
            .group_by(ApiUsage.provider)
        )
        rows = (await session.exec(stmt)).all()
        for provider, count, cost, in_tok, out_tok in rows:
            log.info(
                "aggregate_costs %s: %d calls, $%.4f, %d/%d tokens",
                provider,
                count,
                float(cost),
                int(in_tok),
                int(out_tok),
            )


async def cleanup_stale_docs() -> None:
    """`admin.cleanup_stale_docs` — weekly Sun 03:00."""
    from services.document_generator import cleanup_stale

    async with async_session() as session:
        n = await cleanup_stale(session)
        await session.commit()
    log.info("cleanup_stale_docs pruned %d rows", n)


async def daily_db_snapshot() -> None:
    """`admin.daily_db_snapshot` — daily 02:00.

    Phase 1 ships a touch-marker file in `~/.naavik/data/snapshots/` so the
    cron is verifiably running. Real pg_dump piping ships in Phase 6
    observability work.
    """
    from config import settings as app_settings

    raw = app_settings.data_dir
    base = Path(raw).expanduser() if raw.startswith("~") else Path(raw)
    if not base.is_absolute():
        base = base.resolve()
    snapdir = base / "data" / "snapshots"
    snapdir.mkdir(parents=True, exist_ok=True)
    marker = snapdir / f"snapshot-{datetime.now(UTC).strftime('%Y-%m-%d')}.marker"
    marker.write_text(f"snapshot at {datetime.now(UTC).isoformat()}\n")
    log.info("daily_db_snapshot wrote marker %s", marker)


async def refresh_oauth_tokens() -> None:
    """`admin.refresh_oauth_tokens` — every 6h.

    Phase 4 lights this up when Gmail / Outlook / Calendar OAuth ship.
    Wave 6 ships the skeleton so the cron table is complete.
    """
    log.debug("refresh_oauth_tokens — Phase 4 will light this up")


# ── Registration ──────────────────────────────────────────────────────


def register_all(scheduler: AsyncIOScheduler) -> None:
    """Register every Wave 6 job. Replaces existing same-id jobs."""
    scheduler.add_job(
        auto_apply,
        IntervalTrigger(minutes=5),
        id="applications.auto_apply",
        name="applications.auto_apply",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        aggregate_costs,
        CronTrigger(hour=0, minute=30, timezone="UTC"),
        id="admin.aggregate_costs",
        name="admin.aggregate_costs",
        replace_existing=True,
        coalesce=True,
    )
    scheduler.add_job(
        cleanup_stale_docs,
        CronTrigger(day_of_week="sun", hour=3, minute=0, timezone="UTC"),
        id="admin.cleanup_stale_docs",
        name="admin.cleanup_stale_docs",
        replace_existing=True,
        coalesce=True,
    )
    scheduler.add_job(
        daily_db_snapshot,
        CronTrigger(hour=2, minute=0, timezone="UTC"),
        id="admin.daily_db_snapshot",
        name="admin.daily_db_snapshot",
        replace_existing=True,
        coalesce=True,
    )
    scheduler.add_job(
        refresh_oauth_tokens,
        IntervalTrigger(hours=6),
        id="admin.refresh_oauth_tokens",
        name="admin.refresh_oauth_tokens",
        replace_existing=True,
        coalesce=True,
    )


def registered_job_ids(scheduler: AsyncIOScheduler) -> list[str]:
    return [j.id for j in scheduler.get_jobs()]


__all__ = [
    "aggregate_costs",
    "auto_apply",
    "cleanup_stale_docs",
    "daily_db_snapshot",
    "refresh_oauth_tokens",
    "register_all",
    "registered_job_ids",
]
