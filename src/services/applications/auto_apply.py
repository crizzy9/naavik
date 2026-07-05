"""Auto-apply queue cron — stage pipeline, honest handoffs, drain/pause.

Split out of the former services/application_service.py in plan 91 Phase 4.2;
behaviour unchanged. Internal calls to shimmed/patched seams go through
`svc()` (the facade) so test interception keeps working.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import (
    AppEventKind,
    Application,
    ApplicationStatus,
    DocsState,
    Job,
    JobQueueState,
    Settings,
    StatusChangeTrigger,
)
from services.applications.common import (
    ApplicationServiceError,
    ValidationError,
    _emit_event,
    svc,
)

log = logging.getLogger(__name__)


@dataclass(slots=True)
class AutoApplyResult:
    processed: int = 0
    submitted: int = 0
    failed: int = 0
    skipped_by_cap: int = 0
    docs_generated: int = 0
    handed_to_user: int = 0


def _stamp_auto_apply(application: Application, **fields: Any) -> None:
    """Merge timestamped state fields into `submission_artifacts["auto_apply"]`.

    The auto-apply pipeline's visible-state contract: every transition writes
    a timestamped marker here (queued_at / docs_ready_at / needs_you_at +
    needs_you_reason / dry_run_at / submitted_at) so Discover and Tracking
    can show WHERE a queued job actually is instead of a silent queue.
    """
    artifacts = dict(application.submission_artifacts or {})
    blob = dict(artifacts.get("auto_apply") or {})
    blob.update(fields)
    artifacts["auto_apply"] = blob
    application.submission_artifacts = artifacts
    application.updated_at = datetime.now(UTC)


def _stamp_auto_apply_artifacts(application: Application, paths: list[str], *, key: str) -> None:
    """Record adapter screenshot evidence (filenames only — served via the
    guarded artifacts route) under `submission_artifacts.auto_apply.<key>`."""
    names = [Path(p).name for p in paths if p]
    if names:
        _stamp_auto_apply(application, **{key: names})


async def _hand_to_user(
    session: AsyncSession,
    application: Application,
    job: Job,
    *,
    reason: str,
) -> None:
    """Flip a queued job to READY_TO_SUBMIT — docs are prepared, but this
    application needs the human (unsupported board, auto-apply off, dry-run,
    screener review, adapter wall). Emits an AppEvent with the reason."""
    now = datetime.now(UTC)
    job.queue_state = JobQueueState.READY_TO_SUBMIT
    job.updated_at = now
    session.add(job)
    _stamp_auto_apply(application, needs_you_at=now.isoformat(), needs_you_reason=reason)
    session.add(application)
    await _emit_event(
        session,
        user_id=application.user_id,
        application_id=application.id,
        kind=AppEventKind.AUTO_APPLY_QUEUED,
        payload={"trigger": "handed_to_user", "reason": reason},
    )
    await session.flush()


def auto_apply_phase(application: Application | None, job: Job | None) -> dict[str, Any] | None:
    """Computed pipeline phase for UI chips.

    Returns `{phase, label, reason, at}` or None when the pair isn't in the
    auto-apply pipeline at all. Phases: queued / generating / docs_ready /
    submitted / needs_you.
    """
    if application is None or job is None:
        return None
    blob = (application.submission_artifacts or {}).get("auto_apply") or {}
    if application.status == ApplicationStatus.APPLIED or (
        job.queue_state == JobQueueState.APPLIED
    ):
        applied_at = application.applied_at.isoformat() if application.applied_at else None
        return {
            "phase": "submitted",
            "label": "submitted",
            "reason": None,
            "at": applied_at or blob.get("submitted_at"),
        }
    if job.queue_state == JobQueueState.READY_TO_SUBMIT:
        return {
            "phase": "needs_you",
            "label": "ready for you",
            "reason": blob.get("needs_you_reason"),
            "at": blob.get("needs_you_at"),
        }
    if job.queue_state == JobQueueState.QUEUED_FOR_AUTO_APPLY:
        if application.docs_state == DocsState.GENERATING:
            return {
                "phase": "generating",
                "label": "docs generating",
                "reason": None,
                "at": blob.get("queued_at"),
            }
        if application.docs_state == DocsState.READY:
            return {
                "phase": "docs_ready",
                "label": "docs ready — submitting next tick",
                "reason": None,
                "at": blob.get("docs_ready_at") or blob.get("queued_at"),
            }
        return {
            "phase": "queued",
            "label": "queued",
            "reason": None,
            "at": blob.get("queued_at"),
        }
    return None


async def process_auto_apply_queue(
    session: AsyncSession,
    *,
    user_id: int | None = None,
    notify_fn=None,
) -> AutoApplyResult:
    """Process queued DRAFTs. Returns a per-run summary.

    For each `Application` in DRAFT with `Job.queue_state=QUEUED_FOR_AUTO_APPLY`:
    1. Validate submittable; if not, leave queued.
    2. Dispatch via ATS.
    3. On failure with `kind ∈ {auth_required, captcha, unknown}`, the cron
       reverts `Job.queue_state` to `SAVED` so it doesn't keep retrying without
       human attention. The DRAFT stays DRAFT and surfaces in the stuck queue.
    """
    out = AutoApplyResult()

    stmt = (
        select(Application, Job)
        .join(Job, Job.id == Application.job_id)
        .where(
            Application.status == ApplicationStatus.DRAFT,
            Application.deleted_at.is_(None),
            Job.queue_state == JobQueueState.QUEUED_FOR_AUTO_APPLY,
        )
    )
    if user_id is not None:
        stmt = stmt.where(Application.user_id == user_id)

    rows = (await session.exec(stmt)).all()

    # Pull settings per-user once for cap enforcement.
    settings_cache: dict[int, Settings] = {}

    async def _settings_for(uid: int) -> Settings:
        if uid in settings_cache:
            return settings_cache[uid]
        s = (await session.exec(select(Settings).where(Settings.user_id == uid))).one_or_none()
        if s is None:
            s = Settings(user_id=uid)
        settings_cache[uid] = s
        return s

    today_count: dict[int, int] = {}

    async def _today_submitted_count(uid: int) -> int:
        if uid in today_count:
            return today_count[uid]
        today_start = datetime.combine(datetime.now(UTC).date(), datetime.min.time(), tzinfo=UTC)
        c = (
            await session.exec(
                select(func.count(Application.id)).where(
                    Application.user_id == uid,
                    Application.status != ApplicationStatus.DRAFT,
                    Application.applied_at >= today_start,
                )
            )
        ).one()
        if isinstance(c, tuple):
            c = c[0]
        today_count[uid] = int(c or 0)
        return today_count[uid]

    # Plan 78 § D.3 — per-board daily counter cache. Keyed by (uid, board.value)
    # so concurrent multi-board submissions count independently. Cron lifetime
    # only — re-queries each cron run.
    today_count_per_board: dict[tuple[int, str], int] = {}

    async def _today_submitted_per_board(uid: int, board_value: str) -> int:
        key = (uid, board_value)
        if key in today_count_per_board:
            return today_count_per_board[key]
        from models import ApplicationBoard

        today_start = datetime.combine(datetime.now(UTC).date(), datetime.min.time(), tzinfo=UTC)
        try:
            board_enum = ApplicationBoard(board_value)
        except ValueError:
            today_count_per_board[key] = 0
            return 0
        c = (
            await session.exec(
                select(func.count(Application.id)).where(
                    Application.user_id == uid,
                    Application.board == board_enum,
                    Application.status != ApplicationStatus.DRAFT,
                    Application.applied_at >= today_start,
                )
            )
        ).one()
        if isinstance(c, tuple):
            c = c[0]
        today_count_per_board[key] = int(c or 0)
        return today_count_per_board[key]

    from services.ats import board_supports_auto_submit

    for application, job in rows:
        out.processed += 1
        s = await _settings_for(application.user_id)

        # Stage 1 — documents. The queue OWNS doc generation now: a queued
        # job with no docs used to fail `validate_submittable` silently on
        # every tick, forever. Generate here (cost-capped); if a background
        # generation is already in flight, wait for the next tick.
        if application.docs_state == DocsState.GENERATING:
            continue
        if application.docs_state in {DocsState.NONE, DocsState.STALE, DocsState.FAILED}:
            from services.generation import generate_bundle

            try:
                bundle = await generate_bundle(session, application, settings=s, job=job)
            except Exception as exc:  # noqa: BLE001 — one bad row must not kill the cron
                log.warning("auto-apply doc generation failed for %s: %s", application.id, exc)
                out.failed += 1
                continue
            if bundle.skipped_reason == "cost_cap_reached":
                out.skipped_by_cap += 1
                continue
            out.docs_generated += 1
            _stamp_auto_apply(application, docs_ready_at=datetime.now(UTC).isoformat())
            session.add(application)
            await session.flush()
        if application.docs_state != DocsState.READY:
            continue

        # Stage 2 — honest handoffs. The user queued this job explicitly, so
        # docs get prepared either way; but if WE can't submit it, say so and
        # hand it over instead of sitting silent.
        if not s.auto_apply_enabled:
            await _hand_to_user(
                session,
                application,
                job,
                reason=(
                    "auto-apply is off in Settings — documents are prepared "
                    "for you to submit manually"
                ),
            )
            out.handed_to_user += 1
            continue
        if not board_supports_auto_submit(application.board):
            board_label = application.board.value if application.board else "manual"
            await _hand_to_user(
                session,
                application,
                job,
                reason=(
                    f"{board_label} has no auto-submit adapter — open the "
                    "posting and apply with the prepared documents"
                ),
            )
            out.handed_to_user += 1
            continue

        # Plan 78 § D.1 — belt-and-suspenders score gate. Right-swipe in
        # Discover already gates upstream, but the score may have drifted
        # between queue + dispatch (re-scoring cron, profile change, etc.).
        # Re-check here against the live threshold; below → pull out of queue.
        threshold = getattr(s, "auto_apply_score_threshold", None)
        job_score = getattr(job, "score", None)
        if threshold is not None and job_score is not None and float(job_score) < float(threshold):
            log.info(
                "auto-apply skipped application %s: score %s below threshold %s",
                application.id,
                job_score,
                threshold,
            )
            job.queue_state = JobQueueState.SAVED
            job.updated_at = datetime.now(UTC)
            session.add(job)
            continue
        if s.auto_apply_daily_cap is not None:
            already = await _today_submitted_count(application.user_id)
            if already >= s.auto_apply_daily_cap:
                out.skipped_by_cap += 1
                continue

        try:
            await svc().validate_submittable(session, application)
        except ValidationError as exc:
            log.info("auto-apply skipped application %s: %s", application.id, exc)
            # Plan 78 § fold-in (0.4.0.22) — visa-incompatible DRAFTs in the
            # queue tight-loop on every cron tick. Pull out of queue + emit
            # AUTO_APPLY_VISA_BLOCKED so the operator can re-evaluate.
            if exc.code == "visa_incompatible":
                job.queue_state = JobQueueState.SAVED
                job.updated_at = datetime.now(UTC)
                session.add(job)
                await _emit_event(
                    session,
                    user_id=application.user_id,
                    application_id=application.id,
                    kind=AppEventKind.AUTO_APPLY_VISA_BLOCKED,
                    payload={"message": str(exc)},
                )
            elif exc.code == "screeners_unreviewed":
                # AI-drafted answers can't review themselves — hand over.
                await _hand_to_user(
                    session,
                    application,
                    job,
                    reason="screener answers need your review before submitting",
                )
                out.handed_to_user += 1
            continue

        # Plan 78 § D.5, rebuilt by item 7 (2026-07): dry-run now produces
        # REAL evidence — `submit_draft(dry_run=True)` drives the actual
        # apply form (navigate + fill + upload + screenshot) and stops
        # short of the final submit click. The stamp-only short-circuit
        # proved nothing about field correctness.
        if getattr(s, "auto_apply_dry_run", False):
            try:
                await svc().submit_draft(
                    session,
                    application.id,
                    triggered_by=StatusChangeTrigger.AUTO_APPLY_SUBMITTED,
                    notify_fn=None,
                    dry_run=True,
                )
            except ApplicationServiceError as exc:
                log.warning("dry-run fill errored on %s: %s", application.id, exc)
            await _hand_to_user(
                session,
                application,
                job,
                reason=(
                    "dry-run — the form was filled and screenshotted but NOT "
                    "submitted; inspect the artifacts, then submit manually or "
                    "turn dry-run off"
                ),
            )
            out.handed_to_user += 1
            continue

        # Plan 78 § D.3 — per-board daily cap check. Operator-configurable
        # JSONB on Settings keyed by ApplicationBoard.value. Empty dict /
        # missing board key = no per-board limit (global cap still applies).
        per_board_caps = getattr(s, "auto_apply_per_board_daily_caps", None) or {}
        if application.board is not None:
            board_cap = per_board_caps.get(application.board.value)
            if board_cap is not None:
                already_board = await _today_submitted_per_board(
                    application.user_id, application.board.value
                )
                if already_board >= int(board_cap):
                    out.skipped_by_cap += 1
                    continue

        try:
            after = await svc().submit_draft(
                session,
                application.id,
                triggered_by=StatusChangeTrigger.AUTO_APPLY_SUBMITTED,
                notify_fn=notify_fn,
            )
        except ApplicationServiceError as exc:
            log.warning("auto-apply errored on %s: %s", application.id, exc)
            out.failed += 1
            continue

        if after.status == ApplicationStatus.APPLIED:
            out.submitted += 1
            _stamp_auto_apply(application, submitted_at=datetime.now(UTC).isoformat())
            session.add(application)
            today_count[application.user_id] = today_count.get(application.user_id, 0) + 1
            # Plan 78 § D.3 — bump per-board counter for in-cron-lifetime caps.
            if application.board is not None:
                key = (application.user_id, application.board.value)
                today_count_per_board[key] = today_count_per_board.get(key, 0) + 1
        else:
            out.failed += 1
            # Persistent failure (CAPTCHA / auth wall / field mismatch) —
            # the docs are good; the submission needs a human. Hand over
            # with the failure message instead of burying it in SAVED.
            failure = (application.submission_artifacts or {}).get("last_failure") or {}
            await _hand_to_user(
                session,
                application,
                job,
                reason=f"submission failed: {failure.get('message', 'unknown error')}",
            )
            out.handed_to_user += 1
    return out


# ── Status transitions (manual override) ────────────────────────────────


async def drain_auto_apply_queue(
    session: AsyncSession,
    *,
    user_id: int,
    reason: str | None = None,
) -> int:
    """Plan 78 § D.4 — global drain: flip every QUEUED_FOR_AUTO_APPLY Job back
    to SAVED for the given user; emit one `AUTO_APPLY_DRAINED` AppEvent per
    drained Application. Returns the count drained.

    Use case: operator flips `Settings.auto_apply_enabled = False` and wants
    to clear the queued backlog so the queue doesn't auto-process if they
    later flip it back ON.
    """
    stmt = (
        select(Application, Job)
        .join(Job, Job.id == Application.job_id)
        .where(
            Application.user_id == user_id,
            Application.status == ApplicationStatus.DRAFT,
            Application.deleted_at.is_(None),
            Job.queue_state == JobQueueState.QUEUED_FOR_AUTO_APPLY,
        )
    )
    rows = (await session.exec(stmt)).all()
    drained = 0
    now = datetime.now(UTC)
    for application, job in rows:
        job.queue_state = JobQueueState.SAVED
        job.updated_at = now
        session.add(job)
        await _emit_event(
            session,
            user_id=user_id,
            application_id=application.id,
            kind=AppEventKind.AUTO_APPLY_DRAINED,
            payload={"reason": reason},
        )
        drained += 1
    if drained:
        await session.flush()
    return drained


async def pause_auto_apply_for_job(
    session: AsyncSession,
    *,
    user_id: int,
    job_id: int,
) -> Job | None:
    """Plan 78 § D.4 — per-job pause: flip Job.queue_state QUEUED_FOR_AUTO_APPLY
    → SAVED if the Job is owned by `user_id` and currently queued. Returns the
    updated Job, or None if not found / not queued.
    """
    job = (
        await session.exec(
            select(Job).where(
                Job.id == job_id,
                Job.user_id == user_id,
                Job.deleted_at.is_(None),
            )
        )
    ).one_or_none()
    if job is None:
        return None
    if job.queue_state != JobQueueState.QUEUED_FOR_AUTO_APPLY:
        return job
    job.queue_state = JobQueueState.SAVED
    job.updated_at = datetime.now(UTC)
    session.add(job)
    await session.flush()
    return job
