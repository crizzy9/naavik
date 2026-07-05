"""DRAFT lifecycle — creation, queueing, retarget, cleanup, discard, manual entry, screener-answer recording.

Split out of the former services/application_service.py in plan 91 Phase 4.2;
behaviour unchanged. Internal calls to shimmed/patched seams go through
`svc()` (the facade) so test interception keeps working.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import (
    AppEventKind,
    Application,
    ApplicationScreenerAnswer,
    ApplicationStatus,
    ClosedReason,
    DocsState,
    Job,
    JobQueueState,
    RecruiterState,
    ReferralState,
    Settings,
    StatusChangeTrigger,
)
from services.applications.auto_apply import _stamp_auto_apply
from services.applications.common import (
    ApplicationServiceError,
    IllegalStateTransition,
    _emit_event,
    svc,
)

log = logging.getLogger(__name__)


async def get_or_create_draft(
    session: AsyncSession,
    *,
    user_id: int,
    job_id: int,
    settings: Settings,
) -> Application:
    """Used by `GET /discover/{job_id}`. Creates a DRAFT row if none exists.

    Never generates documents inline — a GET must not block on LLM + Typst
    (~13s on the dev box). Callers that want eager generation dispatch it
    asynchronously via `services.generation.dispatch` after committing.
    """
    del settings  # signature kept uniform; generation moved out of this path
    existing = await svc().get_application_for_job(session, user_id=user_id, job_id=job_id)
    if existing is not None:
        return existing

    job = (await session.exec(select(Job).where(Job.id == job_id))).one_or_none()
    if job is None:
        raise ApplicationServiceError(f"job {job_id} not found")

    now = datetime.now(UTC)
    draft = Application(
        user_id=user_id,
        job_id=job.id,
        company=job.company,
        role=job.role,
        team=job.team,
        location=job.location,
        salary_min=job.salary_min,
        salary_max=job.salary_max,
        equity_pct=job.equity_pct,
        board=job.board,
        # Resolved apply target when known — adapters build their form URL
        # from external_url, and an aggregator listing can't take a form.
        external_url=job.apply_url or job.url,
        status=ApplicationStatus.DRAFT,
        docs_state=DocsState.NONE,
        referral_state=ReferralState.NONE,
        recruiter_state=RecruiterState.NONE,
        applied_at=None,
        created_at=now,
        updated_at=now,
    )
    try:
        async with session.begin_nested():
            session.add(draft)
            await session.flush()
    except IntegrityError:
        # Lost the SELECT→INSERT race on ix_application_user_job_alive_unique
        # (e.g. double-fired HTMX requests for the same card). The savepoint
        # rollback discards our row; reuse the winner's live row instead of
        # surfacing a UniqueViolation.
        existing = await svc().get_application_for_job(session, user_id=user_id, job_id=job_id)
        if existing is None:
            raise
        return existing

    await _emit_event(
        session,
        user_id=user_id,
        application_id=draft.id,
        kind=AppEventKind.STATUS_CHANGE,
        payload={
            "from": None,
            "to": ApplicationStatus.DRAFT.value,
            "trigger": StatusChangeTrigger.DRAFT_CREATION.value,
        },
    )
    return draft


async def resync_draft_apply_target(session: AsyncSession, job: Job) -> int:
    """Re-point a job's DRAFT applications at its freshly resolved apply target.

    `get_or_create_draft` snapshots `board` + `external_url` from the Job at
    creation. Apply-site resolution can promote `job.board` (LinkedIn →
    Greenhouse) and set `job.apply_url` AFTER a draft exists — without this,
    the draft keeps the aggregator board and Submit refuses ("auth required")
    even though the real target is now known. Only DRAFT rows are touched; a
    submitted application is history and must never be rewritten. Returns the
    number of applications updated (caller flushes/commits).
    """
    stmt = select(Application).where(
        Application.job_id == job.id,
        Application.status == ApplicationStatus.DRAFT,
        Application.deleted_at.is_(None),
    )
    apps = (await session.exec(stmt)).all()
    target_url = job.apply_url or job.url
    changed = 0
    for app in apps:
        if app.board != job.board or app.external_url != target_url:
            app.board = job.board
            app.external_url = target_url
            # A submit failure recorded against the OLD target ("auth required"
            # on the aggregator board) is stale once we re-point — drop it so
            # the review UI doesn't show a contradictory banner. New dict so
            # SQLAlchemy flags the JSON column dirty.
            artifacts = app.submission_artifacts
            if isinstance(artifacts, dict) and "last_failure" in artifacts:
                app.submission_artifacts = {
                    k: v for k, v in artifacts.items() if k != "last_failure"
                } or None
            app.updated_at = datetime.now(UTC)
            session.add(app)
            changed += 1
    return changed


async def queue_auto_apply(
    session: AsyncSession,
    *,
    user_id: int,
    job_id: int,
    settings: Settings,
) -> Application:
    """Right-swipe: create DRAFT (if missing) + flip Job.queue_state."""
    draft = await svc().get_or_create_draft(
        session,
        user_id=user_id,
        job_id=job_id,
        settings=settings,
    )
    job = (await session.exec(select(Job).where(Job.id == job_id))).one_or_none()
    if job is not None:
        job.queue_state = JobQueueState.QUEUED_FOR_AUTO_APPLY
        job.updated_at = datetime.now(UTC)
        session.add(job)
    _stamp_auto_apply(draft, queued_at=datetime.now(UTC).isoformat())
    session.add(draft)

    await _emit_event(
        session,
        user_id=user_id,
        application_id=draft.id,
        kind=AppEventKind.STATUS_CHANGE,
        payload={
            "from": ApplicationStatus.DRAFT.value,
            "to": ApplicationStatus.DRAFT.value,
            "trigger": StatusChangeTrigger.AUTO_APPLY_QUEUED.value,
        },
    )
    await session.flush()
    return draft


# ── Submission (validate + ATS dispatch + state flip) ───────────────────


async def cleanup_stale_drafts(
    session: AsyncSession,
    *,
    older_than_days: int = 30,
) -> int:
    """Archive DRAFTs idle > N days. Returns count archived.

    Plan 53 § A.2 / 0.2.4.01. Mirrors `discard_draft` semantics
    (CLOSED + withdrawn_by_me + soft-delete) but emits a CLEANUP_STALE
    AppEvent so audit trail distinguishes system archival from user
    withdrawal.
    """
    threshold = datetime.now(UTC) - timedelta(days=older_than_days)
    stmt = select(Application).where(
        Application.status == ApplicationStatus.DRAFT,
        Application.deleted_at.is_(None),
        Application.updated_at < threshold,
    )
    rows = (await session.exec(stmt)).all()
    archived = 0
    for app in rows:
        now = datetime.now(UTC)
        app.status = ApplicationStatus.CLOSED
        app.closed_reason = ClosedReason.WITHDRAWN_BY_ME
        app.deleted_at = now
        app.updated_at = now
        session.add(app)
        await _emit_event(
            session,
            user_id=app.user_id,
            application_id=app.id,
            kind=AppEventKind.STATUS_CHANGE,
            payload={
                "from": ApplicationStatus.DRAFT.value,
                "to": ApplicationStatus.CLOSED.value,
                "trigger": StatusChangeTrigger.CLEANUP_STALE.value,
            },
        )
        archived += 1
    if archived:
        await session.flush()
    return archived


async def discard_draft(session: AsyncSession, application_id: int) -> Application:
    """DRAFT → CLOSED `withdrawn_by_me` + soft-delete."""
    application = await svc().get_application(session, application_id)
    if application is None:
        raise ApplicationServiceError(f"application {application_id} not found")
    if application.status != ApplicationStatus.DRAFT:
        raise IllegalStateTransition(f"can only discard DRAFTs (was {application.status.value})")
    now = datetime.now(UTC)
    application.status = ApplicationStatus.CLOSED
    application.closed_reason = ClosedReason.WITHDRAWN_BY_ME
    application.deleted_at = now
    application.updated_at = now
    session.add(application)

    if application.job_id:
        job = (await session.exec(select(Job).where(Job.id == application.job_id))).one_or_none()
        if job is not None and job.queue_state == JobQueueState.QUEUED_FOR_AUTO_APPLY:
            job.queue_state = JobQueueState.SAVED
            job.updated_at = now
            session.add(job)

    await _emit_event(
        session,
        user_id=application.user_id,
        application_id=application.id,
        kind=AppEventKind.STATUS_CHANGE,
        payload={
            "from": ApplicationStatus.DRAFT.value,
            "to": ApplicationStatus.CLOSED.value,
            "trigger": StatusChangeTrigger.DISCARD.value,
            "closed_reason": ClosedReason.WITHDRAWN_BY_ME.value,
        },
    )
    await session.flush()
    return application


# ── Auto-apply queue cron ───────────────────────────────────────────────


async def record_draft_failure(
    session: AsyncSession,
    application_id: int,
    kind: str,
    message: str,
) -> Application | None:
    """Write `submission_artifacts.last_failure` to a DRAFT Application."""
    a = await svc().get_application(session, application_id)
    if a is None:
        return None
    artifacts = dict(a.submission_artifacts or {})
    artifacts["last_failure"] = {
        "kind": kind,
        "message": message,
        "captured_at": datetime.now(UTC).isoformat(),
    }
    artifacts["retry_count"] = int(artifacts.get("retry_count") or 0) + 1
    a.submission_artifacts = artifacts
    a.updated_at = datetime.now(UTC)
    session.add(a)
    await session.flush()
    return a


async def create_manual(
    session: AsyncSession,
    *,
    user_id: int,
    company: str,
    role: str,
    team: str | None = None,
    location: str | None = None,
    salary_min: int | None = None,
    salary_max: int | None = None,
    notes: str | None = None,
) -> Application:
    """Create an APPLIED Application from the manual-entry form.

    Uses `board = ApplicationBoard.MANUAL` and stamps `applied_at = now`.
    Emits a STATUS_CHANGE AppEvent so the Tracking timeline carries the
    transition.
    """
    from models import ApplicationBoard  # local import to avoid circular

    now = datetime.now(UTC)
    a = Application(
        user_id=user_id,
        job_id=None,
        company=company,
        role=role,
        team=team,
        location=location,
        salary_min=salary_min,
        salary_max=salary_max,
        applied_at=now,
        board=ApplicationBoard.MANUAL,
        external_url=None,
        status=ApplicationStatus.APPLIED,
        docs_state=DocsState.NONE,
        referral_state=ReferralState.NONE,
        recruiter_state=RecruiterState.NONE,
        submission_artifacts={"board_application_id": None, "manual": True},
        notes=notes,
        created_at=now,
        updated_at=now,
    )
    session.add(a)
    await session.flush()
    await _emit_event(
        session,
        user_id=user_id,
        application_id=a.id,
        kind=AppEventKind.STATUS_CHANGE,
        payload={
            "from": None,
            "to": ApplicationStatus.APPLIED.value,
            "trigger": "manual",
        },
    )
    return a


async def record_screener_answer(
    session: AsyncSession,
    answer_id: int,
    body: str,
    *,
    owner_user_id: int | None = None,
) -> ApplicationScreenerAnswer | None:
    """Update an ApplicationScreenerAnswer body + stamp reviewed_at.

    Plan 75 / 0.3.3.15. `owner_user_id` enforces the IDOR boundary on
    writes — when set, returns None for cross-user attempts so the route
    surfaces a clean 404. `None` preserves fake-session bypass.
    """
    if owner_user_id is None:
        stmt = select(ApplicationScreenerAnswer).where(ApplicationScreenerAnswer.id == answer_id)
    else:
        stmt = (
            select(ApplicationScreenerAnswer)
            .join(Application, ApplicationScreenerAnswer.application_id == Application.id)
            .where(
                ApplicationScreenerAnswer.id == answer_id,
                Application.user_id == owner_user_id,
            )
        )
    a = (await session.exec(stmt)).one_or_none()
    if a is None:
        return None
    now = datetime.now(UTC)
    a.answer = body
    a.reviewed_at = now
    a.updated_at = now
    session.add(a)
    await session.flush()
    return a


# ── Submission-result observability (plan 54 / 0.2.5.02) ───────────────
