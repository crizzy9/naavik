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


async def cleanup_stale_drafts() -> None:
    """`admin.cleanup_stale_drafts` — weekly Sun 03:30 (plan 53 / 0.2.4.01).

    Soft-deletes DRAFT Applications idle > 30 days. Mirrors discard_draft
    semantics (CLOSED + withdrawn_by_me + deleted_at) and emits a
    STATUS_CHANGE AppEvent with trigger=CLEANUP_STALE.
    """
    from services.application_service import cleanup_stale_drafts as svc

    async with async_session() as session:
        n = await svc(session)
        await session.commit()
    log.info("cleanup_stale_drafts archived %d rows", n)


async def cleanup_revoked_jwts() -> None:
    """`admin.cleanup_revoked_jwts` — daily 03:30 UTC (plan 50 / 0.2.1.04)."""
    from services.auth import cleanup_expired_revoked_jwts

    async with async_session() as session:
        n = await cleanup_expired_revoked_jwts(session)
        await session.commit()
    log.info("cleanup_revoked_jwts pruned %d rows", n)


async def expire_retiring_signing_keys() -> None:
    """`admin.expire_retiring_signing_keys` — nightly 04:00 UTC.

    Plan 62 (0.2.7.07). Sweeps `tenant_signing_key` rows in RETIRING and
    flips to RETIRED once `retired_at + Settings.jwt_rotation_grace_days`
    has passed. Settings rows are read per-tenant; the grace window
    defaults to 7 days when no per-tenant override exists.
    """
    from models import Settings as SettingsRow
    from services.jwt_rotation_service import expire_retiring_keys

    async with async_session() as session:
        # Scalar select to avoid hydrating JSONB columns the cron doesn't need.
        rows = (
            await session.exec(select(SettingsRow.user_id, SettingsRow.jwt_rotation_grace_days))
        ).all()
        grace_by_tenant: dict[int, int] = {}
        for user_id, grace in rows:
            # Self-host: user_id == tenant_id (1:1 until plan 0.8.0.NN
            # introduces a proper Tenant↔User mapping).
            grace_by_tenant[int(user_id)] = int(grace)
        flipped = await expire_retiring_keys(session, grace_days_by_tenant=grace_by_tenant)
        await session.commit()
    log.info("expire_retiring_signing_keys flipped=%d", flipped)


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


async def embed_pending_jobs() -> None:
    """`embeddings.embed_pending_jobs` — nightly 02:00 UTC (plan 61 / 0.2.7.16).

    For each user with `Settings.semantic_match_enabled = True`, embed every
    Job whose JobEmbedding is missing or stale. Respects the daily cost cap
    via `llm_tracker.tracked_call` (which logs ApiUsage rows the cap reads).
    """
    from models import Job, Settings
    from services import embedding_service

    async with async_session() as session:
        users_stmt = select(Settings).where(Settings.semantic_match_enabled.is_(True))
        users = (await session.exec(users_stmt)).all()

        total_processed = 0
        total_embedded = 0
        for settings_row in users:
            jobs_stmt = select(Job).where(
                Job.user_id == settings_row.user_id,
                Job.deleted_at.is_(None),
            )
            jobs = (await session.exec(jobs_stmt)).all()
            for job in jobs:
                total_processed += 1
                if not await embedding_service.needs_embedding(
                    session, job=job, settings=settings_row
                ):
                    continue
                row = await embedding_service.embed_job(session, job=job, settings=settings_row)
                if row is not None:
                    total_embedded += 1
            await session.commit()
    log.info(
        "embed_pending_jobs processed=%d embedded=%d users=%d",
        total_processed,
        total_embedded,
        len(users),
    )


async def embed_orphan_sweep() -> None:
    """`embeddings.embed_orphan_sweep` — nightly 03:00 UTC (plan 61 / 0.2.7.16).

    DELETE JobEmbedding rows whose Job is gone or soft-deleted. Idempotent.
    """
    from services import embedding_service

    async with async_session() as session:
        deleted = await embedding_service.delete_orphan_embeddings(session)
        await session.commit()
    log.info("embed_orphan_sweep deleted=%d", deleted)


async def score_pending() -> None:
    """`jobs.score_pending` — every 15min (plan 65 / 0.3.0.06; BACKEND.md § I.1).

    Scores jobs with `Job.score == 0.0` for any user with
    `Settings.semantic_match_enabled = True`. Idempotent: a job that's
    already scored has `Job.score != 0.0` so the next run skips it.
    """
    from services.scorer.orchestrator import score_unscored_jobs

    async with async_session() as session:
        n = await score_unscored_jobs(session)
        await session.commit()
    log.info("score_pending scored=%d", n)


async def score_recompute_stale() -> None:
    """`score.recompute_stale` — nightly 03:30 UTC (plan 65 / 0.3.0.06).

    Re-scores jobs where `Profile.updated_at > Job.match_breakdown.scored_at`.
    Postgres-only via the JSONB extractor; sqlite returns 0 (test stubs
    exercise the routing via mocks).
    """
    from services.scorer.orchestrator import rescore_stale_jobs

    async with async_session() as session:
        n = await rescore_stale_jobs(session)
        await session.commit()
    log.info("score_recompute_stale scored=%d", n)


async def score_aggregate_daily() -> None:
    """`score.aggregate_daily` — daily 03:35 UTC (plan 73 / 0.3.2.03; slot shifted from 03:30 in plan 75 / 0.3.3.19 to avoid collision with `score.recompute_stale`).

    For every Profile row, recompute the per-role-family 30-day score
    trend blob from `Job.match_breakdown.scored_at` and write it to
    `Profile.score_history`. Pure DB aggregation — no LLM calls.
    """
    from services import scoring_history

    async with async_session() as session:
        # Pull every live profile; score-history is per-user.
        from models import Profile

        rows = (
            await session.exec(select(Profile.user_id).where(Profile.deleted_at.is_(None)))
        ).all()
        updated = 0
        for user_id in rows:
            blob = await scoring_history.update_profile_score_history(session, int(user_id))
            if blob is not None:
                updated += 1
        await session.commit()
    log.info("score_aggregate_daily users=%d updated=%d", len(rows), updated)


async def embed_pending_profiles() -> None:
    """`embeddings.embed_pending_profiles` — nightly 02:30 UTC (plan 65 / 0.3.0.03).

    For each user with `Settings.semantic_match_enabled = True`, ensure their
    ProfileEmbedding is current. Idempotent via `_profile_content_hash` —
    no-op when text + model match. Best-effort: errors are logged + moved on.
    """
    from models import Profile, Settings
    from services import embedding_service

    async with async_session() as session:
        users_stmt = select(Settings).where(Settings.semantic_match_enabled.is_(True))
        users = (await session.exec(users_stmt)).all()

        total_processed = 0
        total_embedded = 0
        for settings_row in users:
            profile = (
                await session.exec(select(Profile).where(Profile.user_id == settings_row.user_id))
            ).one_or_none()
            if profile is None:
                continue
            total_processed += 1
            if not await embedding_service.needs_profile_embedding(
                session, profile=profile, settings=settings_row
            ):
                continue
            row = await embedding_service.embed_profile(
                session, profile=profile, settings=settings_row
            )
            if row is not None:
                total_embedded += 1
            await session.commit()
    log.info(
        "embed_pending_profiles processed=%d embedded=%d users=%d",
        total_processed,
        total_embedded,
        len(users),
    )


async def sync_emails() -> None:
    """`tracking.sync_emails` — every 10min (plan 90 / 0.5.0.01).

    Fan-out per `EmailAccount`. Best-effort — per-account failures bump
    `connection_failure_count` + flip status; no exception propagates.
    """
    from services.email_sync import sync_all_accounts

    async with async_session() as session:
        result = await sync_all_accounts(session)
        await session.commit()
    log.info(
        "sync_emails accounts=%d fetched=%d new=%d failed=%d",
        result.accounts,
        result.fetched,
        result.new,
        result.failed,
    )


async def classify_emails() -> None:
    """`tracking.classify_emails` — every 10min offset +2min (plan 90 / 0.5.0.02).

    Picks unclassified EmailMessage rows. Graceful no-LLM degrade marks rows
    `unclassified_reason=NO_PROVIDER_CONFIGURED` so they retry post-LLM-config.
    """
    from services.email_application_inference import infer_unprocessed
    from services.email_classifier import classify_unprocessed

    async with async_session() as session:
        n = await classify_unprocessed(session, limit=200)
        # Item 5 (2026-07): application-receipt inference rides the same
        # tick — deterministic, so it works even when classification
        # degraded to NO_PROVIDER_CONFIGURED.
        inferred = await infer_unprocessed(session, limit=200)
        await session.commit()
    log.info("classify_emails classified=%d inferred_applications=%d", n, inferred)


async def sync_calendars() -> None:
    """`tracking.sync_calendars` — every 45min (item 11, 2026-07).

    Re-fetches every connected secret-ICS calendar. Per-connection failures
    flip `status=fetch_failed` + record `last_error`; nothing propagates.
    """
    from sqlmodel import select as _select

    from models import CalendarConnection
    from services import calendar_sync

    async with async_session() as session:
        connections = (
            await session.exec(
                _select(CalendarConnection).where(CalendarConnection.deleted_at.is_(None))
            )
        ).all()
        total = new = failed = 0
        for connection in connections:
            t, n = await calendar_sync.sync_connection(session, connection)
            total += t
            new += n
            if connection.status != "ok":
                failed += 1
        await session.commit()
    log.info(
        "sync_calendars connections=%d events=%d new=%d failed=%d",
        len(connections),
        total,
        new,
        failed,
    )


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
        cleanup_stale_drafts,
        CronTrigger(day_of_week="sun", hour=3, minute=30, timezone="UTC"),
        id="admin.cleanup_stale_drafts",
        name="admin.cleanup_stale_drafts",
        replace_existing=True,
        coalesce=True,
    )
    scheduler.add_job(
        cleanup_revoked_jwts,
        CronTrigger(hour=3, minute=30, timezone="UTC"),
        id="admin.cleanup_revoked_jwts",
        name="admin.cleanup_revoked_jwts",
        replace_existing=True,
        coalesce=True,
    )
    # Plan 62 (0.2.7.07): nightly RETIRING → RETIRED sweep.
    scheduler.add_job(
        expire_retiring_signing_keys,
        CronTrigger(hour=4, minute=0, timezone="UTC"),
        id="admin.expire_retiring_signing_keys",
        name="admin.expire_retiring_signing_keys",
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
    # Plan 61 (0.2.7.16): semantic-match nightly batch + orphan sweep.
    # Gated per-user by Settings.semantic_match_enabled; cron runs always so
    # the moment a user enables the toggle it picks up at the next tick.
    scheduler.add_job(
        embed_pending_jobs,
        CronTrigger(hour=2, minute=0, timezone="UTC"),
        id="embeddings.embed_pending_jobs",
        name="embeddings.embed_pending_jobs",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        embed_orphan_sweep,
        CronTrigger(hour=3, minute=0, timezone="UTC"),
        id="embeddings.embed_orphan_sweep",
        name="embeddings.embed_orphan_sweep",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    # Plan 65 (0.3.0.03): nightly Profile embedding refresh.
    scheduler.add_job(
        embed_pending_profiles,
        CronTrigger(hour=2, minute=30, timezone="UTC"),
        id="embeddings.embed_pending_profiles",
        name="embeddings.embed_pending_profiles",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    # Plan 65 (0.3.0.06): score pending + recompute-stale crons.
    scheduler.add_job(
        score_pending,
        IntervalTrigger(minutes=15),
        id="jobs.score_pending",
        name="jobs.score_pending",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        score_recompute_stale,
        CronTrigger(hour=3, minute=30, timezone="UTC"),
        id="score.recompute_stale",
        name="score.recompute_stale",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    # Plan 73 (0.3.2.03) + plan 75 (0.3.3.19): daily per-role-family score
    # trend rollup. 5-minute offset from recompute-stale (03:30 UTC) avoids
    # the theoretical concurrency window; APScheduler doesn't guarantee
    # ordering within a single cron slot.
    scheduler.add_job(
        score_aggregate_daily,
        CronTrigger(hour=3, minute=35, timezone="UTC"),
        id="score.aggregate_daily",
        name="score.aggregate_daily",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    # Plan 90 (0.5.0.01 + 0.5.0.02): email sync + classify crons.
    # 10-min sync; classify cron also runs every 10min but offset +2min so it
    # picks up DB-flushed messages from the prior sync tick. No trigger
    # chaining — two independent APScheduler jobs.
    scheduler.add_job(
        sync_emails,
        IntervalTrigger(minutes=10),
        id="tracking.sync_emails",
        name="tracking.sync_emails",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        classify_emails,
        IntervalTrigger(minutes=10),
        id="tracking.classify_emails",
        name="tracking.classify_emails",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(UTC) + timedelta(minutes=2),
    )

    # Item 11 (2026-07): read-only ICS calendar sync.
    scheduler.add_job(
        sync_calendars,
        IntervalTrigger(minutes=45),
        id="tracking.sync_calendars",
        name="tracking.sync_calendars",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    # Phase 2 plan 35 (0.2.0.10): six per-source scraping crons.
    from . import scraping

    scraping.register_scraping_jobs(scheduler)


def registered_job_ids(scheduler: AsyncIOScheduler) -> list[str]:
    return [j.id for j in scheduler.get_jobs()]


__all__ = [
    "aggregate_costs",
    "auto_apply",
    "classify_emails",
    "cleanup_revoked_jwts",
    "cleanup_stale_docs",
    "cleanup_stale_drafts",
    "daily_db_snapshot",
    "embed_orphan_sweep",
    "embed_pending_jobs",
    "embed_pending_profiles",
    "expire_retiring_signing_keys",
    "refresh_oauth_tokens",
    "register_all",
    "registered_job_ids",
    "score_aggregate_daily",
    "score_pending",
    "score_recompute_stale",
    "sync_emails",
]
