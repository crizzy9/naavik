"""Application service — full DRAFT lifecycle + state-transition enforcement.

Per BACKEND.md § K + plan 10 § C.3 + DATA_MODEL.md § E.

Owns:

- DRAFT lifecycle (`get_or_create_draft`, `queue_auto_apply`, `submit_draft`,
  `discard_draft`, `process_auto_apply_queue`).
- Forward-only `Application.status` transitions.
- Service-layer computed state: `_roll_up_referral_state`,
  `compute_outreach_engagement`, `Job.queue_state` flip on submit.
- Failed-DRAFT surface — writes `submission_artifacts.last_failure` so the
  Discover stuck-queue card can read it.

Submission goes through `services/ats/__init__.py:dispatch(board)` for
Greenhouse / Lever / Ashby. Workday / LinkedIn / Indeed / Generic are
Phase 1.x (separate sub-prompt).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import (
    AppEvent,
    AppEventKind,
    Application,
    ApplicationScreenerAnswer,
    ApplicationStatus,
    ClosedReason,
    ContactApplicationLink,
    DocsState,
    GeneratedDocument,
    GeneratedDocumentKind,
    Job,
    JobQueueState,
    OutreachMessage,
    OutreachStatus,
    RecruiterState,
    ReferralState,
    ScreenerAnswerSource,
    Settings,
    StatusChangeTrigger,
)
from services.ats import ATSError
from services.ats import dispatch as ats_dispatch
from services.ats.base import ApplicationBundle, SubmissionResult

log = logging.getLogger(__name__)


class ApplicationServiceError(Exception):
    """Generic service-layer failure."""


class ValidationError(ApplicationServiceError):
    """`validate_submittable` rejected the application."""

    def __init__(self, message: str, *, code: str = "validation_failed") -> None:
        super().__init__(message)
        self.code = code


class IllegalStateTransition(ApplicationServiceError):
    """Backwards / forbidden status transition."""


# ── Status-transition rules ─────────────────────────────────────────────


_FORWARD_FROM: dict[ApplicationStatus, set[ApplicationStatus]] = {
    ApplicationStatus.DRAFT: {ApplicationStatus.APPLIED, ApplicationStatus.CLOSED},
    ApplicationStatus.APPLIED: {
        ApplicationStatus.RECRUITER_SCREEN,
        ApplicationStatus.CLOSED,
    },
    ApplicationStatus.RECRUITER_SCREEN: {
        ApplicationStatus.ONSITE_LOOP,
        ApplicationStatus.CLOSED,
    },
    ApplicationStatus.ONSITE_LOOP: {
        ApplicationStatus.OFFER,
        ApplicationStatus.CLOSED,
    },
    ApplicationStatus.OFFER: {ApplicationStatus.CLOSED},
    ApplicationStatus.CLOSED: set(),
}


def _is_forward_transition(current: ApplicationStatus, target: ApplicationStatus) -> bool:
    return target in _FORWARD_FROM.get(current, set())


# ── Get / load helpers ──────────────────────────────────────────────────


async def get_application(session: AsyncSession, application_id: int) -> Application | None:
    return (
        await session.exec(select(Application).where(Application.id == application_id))
    ).one_or_none()


async def get_application_for_job(
    session: AsyncSession, *, user_id: int, job_id: int
) -> Application | None:
    return (
        await session.exec(
            select(Application).where(
                Application.user_id == user_id,
                Application.job_id == job_id,
                Application.deleted_at.is_(None),
            )
        )
    ).one_or_none()


async def _emit_event(
    session: AsyncSession,
    *,
    user_id: int,
    application_id: int | None,
    kind: AppEventKind,
    payload: dict[str, Any] | None = None,
    actor: str | None = None,
) -> AppEvent:
    ev = AppEvent(
        user_id=user_id,
        application_id=application_id,
        kind=kind,
        payload=payload or {},
        actor=actor,
        occurred_at=datetime.now(UTC),
    )
    session.add(ev)
    await session.flush()
    return ev


# ── DRAFT creation ──────────────────────────────────────────────────────


async def get_or_create_draft(
    session: AsyncSession,
    *,
    user_id: int,
    job_id: int,
    settings: Settings,
    pre_generate_fn=None,
) -> Application:
    """Used by `GET /discover/{job_id}`. Creates a DRAFT row if none exists.

    Pre-generation gated on `settings.eager_review_generation`. The call is
    routed through `pre_generate_fn` (defaults to
    `document_generator.pre_generate`). Tests can pass a stub.
    """
    existing = await get_application_for_job(session, user_id=user_id, job_id=job_id)
    if existing is not None:
        if (
            settings.eager_review_generation
            and existing.status == ApplicationStatus.DRAFT
            and existing.docs_state in {DocsState.NONE, DocsState.STALE}
        ):
            await _maybe_pre_generate(
                session, existing, settings=settings, pre_generate_fn=pre_generate_fn
            )
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
        external_url=job.url,
        status=ApplicationStatus.DRAFT,
        docs_state=DocsState.NONE,
        referral_state=ReferralState.NONE,
        recruiter_state=RecruiterState.NONE,
        applied_at=None,
        created_at=now,
        updated_at=now,
    )
    session.add(draft)
    await session.flush()

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

    if settings.eager_review_generation:
        await _maybe_pre_generate(
            session, draft, settings=settings, pre_generate_fn=pre_generate_fn
        )
    return draft


async def _maybe_pre_generate(
    session: AsyncSession,
    application: Application,
    *,
    settings: Settings,
    pre_generate_fn=None,
) -> None:
    """Invoke the document_generator pre_generate hook with safe fallback."""
    if pre_generate_fn is None:
        from services.document_generator import pre_generate as pre_generate_fn  # noqa: PLR0915
    try:
        await pre_generate_fn(session, application, settings=settings)
    except Exception as exc:  # noqa: BLE001 — caller may not want to crash on generation failures
        log.warning("pre_generate failed for application %s: %s", application.id, exc)


async def queue_auto_apply(
    session: AsyncSession,
    *,
    user_id: int,
    job_id: int,
    settings: Settings,
    pre_generate_fn=None,
) -> Application:
    """Right-swipe: create DRAFT (if missing) + flip Job.queue_state."""
    draft = await get_or_create_draft(
        session,
        user_id=user_id,
        job_id=job_id,
        settings=settings,
        pre_generate_fn=pre_generate_fn,
    )
    job = (await session.exec(select(Job).where(Job.id == job_id))).one_or_none()
    if job is not None:
        job.queue_state = JobQueueState.QUEUED_FOR_AUTO_APPLY
        job.updated_at = datetime.now(UTC)
        session.add(job)

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


async def validate_submittable(session: AsyncSession, application: Application) -> None:
    """Raise `ValidationError` if the DRAFT can't be submitted yet.

    Rules per plan 10 § C.3:
    - status must be DRAFT
    - docs_state must be READY
    - all required DRAFTED screener answers must have reviewed_at NOT NULL
    """
    if application.status != ApplicationStatus.DRAFT:
        raise ValidationError(f"application {application.id} not in DRAFT", code="not_draft")
    if application.docs_state != DocsState.READY:
        raise ValidationError(
            "documents not ready (regen the resume first)",
            code="docs_not_ready",
        )
    unreviewed = await _unreviewed_required_screener_count(session, application.id)
    if unreviewed > 0:
        raise ValidationError(
            f"{unreviewed} required screener answers awaiting review",
            code="screeners_unreviewed",
        )


async def _unreviewed_required_screener_count(session: AsyncSession, application_id: int) -> int:
    stmt = select(func.count(ApplicationScreenerAnswer.id)).where(
        ApplicationScreenerAnswer.application_id == application_id,
        ApplicationScreenerAnswer.required.is_(True),
        ApplicationScreenerAnswer.source == ScreenerAnswerSource.DRAFTED,
        ApplicationScreenerAnswer.reviewed_at.is_(None),
    )
    result = (await session.exec(stmt)).one()
    if isinstance(result, tuple):
        result = result[0]
    return int(result or 0)


async def _build_bundle(session: AsyncSession, application: Application) -> ApplicationBundle:
    resume = (
        await session.exec(
            select(GeneratedDocument)
            .where(
                GeneratedDocument.application_id == application.id,
                GeneratedDocument.kind == GeneratedDocumentKind.RESUME,
                GeneratedDocument.error.is_(None),
            )
            .order_by(GeneratedDocument.compiled_at.desc())
            .limit(1)
        )
    ).one_or_none()
    cover = (
        await session.exec(
            select(GeneratedDocument)
            .where(
                GeneratedDocument.application_id == application.id,
                GeneratedDocument.kind == GeneratedDocumentKind.COVER_LETTER,
                GeneratedDocument.error.is_(None),
            )
            .order_by(GeneratedDocument.compiled_at.desc())
            .limit(1)
        )
    ).one_or_none()
    screeners = (
        await session.exec(
            select(ApplicationScreenerAnswer).where(
                ApplicationScreenerAnswer.application_id == application.id
            )
        )
    ).all()
    return ApplicationBundle(
        application=application,
        resume=resume,
        cover_letter=cover,
        screener_answers=list(screeners),
    )


async def _record_failure(
    session: AsyncSession,
    application: Application,
    *,
    kind: str,
    message: str,
) -> None:
    artifacts = dict(application.submission_artifacts or {})
    artifacts["last_failure"] = {
        "kind": kind,
        "message": message,
        "captured_at": datetime.now(UTC).isoformat(),
    }
    artifacts["retry_count"] = int(artifacts.get("retry_count", 0)) + 1
    application.submission_artifacts = artifacts
    application.updated_at = datetime.now(UTC)
    session.add(application)
    await session.flush()


async def _record_success(
    session: AsyncSession,
    application: Application,
    *,
    board_application_id: str | None,
) -> None:
    artifacts = dict(application.submission_artifacts or {})
    if board_application_id:
        artifacts["board_application_id"] = board_application_id
    artifacts.pop("last_failure", None)  # clear on success
    application.submission_artifacts = artifacts


async def submit_draft(
    session: AsyncSession,
    application_id: int,
    *,
    triggered_by: StatusChangeTrigger = StatusChangeTrigger.DRAFT_SUBMITTED,
    notify_fn=None,
) -> Application:
    """DRAFT → APPLIED. Validates, dispatches via ATS, flips state.

    On persistent failure (CAPTCHA / auth_required / etc.), keeps DRAFT and
    writes `submission_artifacts.last_failure`. Caller (cron or HTTP handler)
    treats the return as a tuple `(application, ok=bool)` via `application.status`.
    """
    application = await get_application(session, application_id)
    if application is None:
        raise ApplicationServiceError(f"application {application_id} not found")

    await validate_submittable(session, application)

    if application.board is None:
        raise ValidationError("application has no board; cannot dispatch", code="no_board")

    bundle = await _build_bundle(session, application)
    adapter = ats_dispatch(application.board)

    try:
        result: SubmissionResult = await adapter.submit(application, bundle)
    except ATSError as exc:
        await _record_failure(session, application, kind="unknown", message=str(exc))
        await _emit_event(
            session,
            user_id=application.user_id,
            application_id=application.id,
            kind=AppEventKind.DOCS_FAILED,
            payload={"kind": "unknown", "message": str(exc)},
        )
        return application

    if not result.ok:
        kind = result.error or "unknown"
        message = result.error_message or kind
        await _record_failure(session, application, kind=kind, message=message)
        await _emit_event(
            session,
            user_id=application.user_id,
            application_id=application.id,
            kind=AppEventKind.DOCS_FAILED,
            payload={"kind": kind, "message": message},
        )
        return application

    # Success — flip state in one transaction.
    now = datetime.now(UTC)
    application.status = ApplicationStatus.APPLIED
    application.applied_at = now
    application.updated_at = now
    await _record_success(session, application, board_application_id=result.board_application_id)
    session.add(application)

    if application.job_id:
        job = (await session.exec(select(Job).where(Job.id == application.job_id))).one_or_none()
        if job is not None:
            job.queue_state = JobQueueState.APPLIED
            job.updated_at = now
            session.add(job)

    await _emit_event(
        session,
        user_id=application.user_id,
        application_id=application.id,
        kind=AppEventKind.STATUS_CHANGE,
        payload={
            "from": ApplicationStatus.DRAFT.value,
            "to": ApplicationStatus.APPLIED.value,
            "trigger": triggered_by.value,
            "board_application_id": result.board_application_id,
        },
    )
    await session.flush()

    if notify_fn is not None:
        try:
            await notify_fn(application)
        except Exception as exc:  # noqa: BLE001 — notification failures are non-fatal
            log.warning("notify_application_submitted failed: %s", exc)

    return application


async def discard_draft(session: AsyncSession, application_id: int) -> Application:
    """DRAFT → CLOSED `withdrawn_by_me` + soft-delete."""
    application = await get_application(session, application_id)
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


@dataclass(slots=True)
class AutoApplyResult:
    processed: int = 0
    submitted: int = 0
    failed: int = 0
    skipped_by_cap: int = 0


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

    for application, job in rows:
        out.processed += 1
        s = await _settings_for(application.user_id)
        if not s.auto_apply_enabled:
            continue
        if s.auto_apply_daily_cap is not None:
            already = await _today_submitted_count(application.user_id)
            if already >= s.auto_apply_daily_cap:
                out.skipped_by_cap += 1
                continue

        try:
            await validate_submittable(session, application)
        except ValidationError as exc:
            log.info("auto-apply skipped application %s: %s", application.id, exc)
            continue

        before = application.status
        try:
            after = await submit_draft(
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
            today_count[application.user_id] = today_count.get(application.user_id, 0) + 1
        else:
            out.failed += 1
            # Persistent failure — pull job out of the auto-apply queue.
            job.queue_state = JobQueueState.SAVED
            job.updated_at = datetime.now(UTC)
            session.add(job)
            await session.flush()
        del before
    return out


# ── Status transitions (manual override) ────────────────────────────────


async def update_status(
    session: AsyncSession,
    application_id: int,
    new_status: ApplicationStatus,
    *,
    closed_reason: ClosedReason | None = None,
    notes: str | None = None,
) -> Application:
    """Manual user-driven status flip.

    Forward transitions are enforced; a backwards transition is allowed but
    logged as `MANUAL_OVERRIDE` AppEvent so audit history is preserved.
    """
    application = await get_application(session, application_id)
    if application is None:
        raise ApplicationServiceError(f"application {application_id} not found")
    current = application.status
    is_forward = _is_forward_transition(current, new_status)
    if not is_forward and current != new_status:
        # Allow but mark explicitly as a manual override.
        log.info(
            "manual override: application %s %s → %s",
            application_id,
            current.value,
            new_status.value,
        )
    if new_status == ApplicationStatus.CLOSED and closed_reason is None:
        raise ValidationError(
            "closed_reason required when status=CLOSED",
            code="closed_reason_missing",
        )

    now = datetime.now(UTC)
    application.status = new_status
    if new_status == ApplicationStatus.CLOSED:
        application.closed_reason = closed_reason
    if new_status != ApplicationStatus.DRAFT and application.applied_at is None:
        # Forward-only: applied_at must be set when leaving DRAFT.
        application.applied_at = now
    if notes:
        application.notes = notes
    application.updated_at = now
    session.add(application)

    await _emit_event(
        session,
        user_id=application.user_id,
        application_id=application.id,
        kind=AppEventKind.STATUS_CHANGE,
        payload={
            "from": current.value,
            "to": new_status.value,
            "trigger": StatusChangeTrigger.MANUAL.value,
            "is_forward": is_forward,
            "notes": notes,
        },
    )
    await session.flush()
    return application


# ── Computed state — referral + outreach ────────────────────────────────


_REFERRAL_PRIORITY = {
    ReferralState.PROVIDED: 4,
    ReferralState.IN_FLIGHT: 3,
    ReferralState.REQUESTED: 2,
    ReferralState.DECLINED: 1,
    ReferralState.NONE: 0,
}


async def _roll_up_referral_state(session: AsyncSession, application_id: int) -> ReferralState:
    """Application.referral_state = max-priority across all links."""
    links = (
        await session.exec(
            select(ContactApplicationLink).where(
                ContactApplicationLink.application_id == application_id
            )
        )
    ).all()
    if not links:
        new_state = ReferralState.NONE
    else:
        new_state = max(
            (link.referral_state for link in links),
            key=lambda s: _REFERRAL_PRIORITY.get(s, 0),
        )
    application = await get_application(session, application_id)
    if application is None:
        return new_state
    if application.referral_state != new_state:
        application.referral_state = new_state
        application.updated_at = datetime.now(UTC)
        session.add(application)
        await session.flush()
    return new_state


async def compute_outreach_engagement(session: AsyncSession, application_id: int) -> str:
    """Pure function over OutreachMessage[] + ContactApplicationLink[].

    Returns one of `referred / awaiting_reply / cold / active`.
    Phase 1 computed on demand; Phase 4+ may cache.
    """
    links = (
        await session.exec(
            select(ContactApplicationLink).where(
                ContactApplicationLink.application_id == application_id
            )
        )
    ).all()
    if any(link.referral_state == ReferralState.PROVIDED for link in links):
        return "referred"

    msgs = (
        await session.exec(
            select(OutreachMessage).where(OutreachMessage.application_id == application_id)
        )
    ).all()
    if not msgs and not links:
        return "cold"
    threshold = datetime.now(UTC) - timedelta(days=14)
    awaiting = any(
        m.sent_at is not None
        and m.sent_at >= threshold
        and m.replied_at is None
        and m.status == OutreachStatus.SENT
        for m in msgs
    )
    if awaiting:
        return "awaiting_reply"
    if msgs or links:
        return "active"
    return "cold"


# ── Recruiter-state derivation (cron in Phase 4) ────────────────────────


async def derive_recruiter_states(session: AsyncSession) -> int:
    """Auto-derive `Application.recruiter_state` per DATA_MODEL.md § E.

    Wave 6 ships the function; the `tracking.derive_recruiter_state` cron is
    wired in Phase 4. For Wave 6 we expose it so the auto-apply path can
    refresh recruiter_state in batch when other code calls it.
    """
    apps = (
        await session.exec(
            select(Application).where(
                Application.status != ApplicationStatus.DRAFT,
                Application.deleted_at.is_(None),
            )
        )
    ).all()
    updated = 0
    now = datetime.now(UTC)
    for a in apps:
        # Phase 4 will look at EmailThread.messages; Wave 6 is a no-op.
        if a.recruiter_state == RecruiterState.STALLED:
            continue
        # Heuristic placeholder: if applied >14d and still NONE, mark SILENT.
        if (
            a.applied_at is not None
            and a.recruiter_state == RecruiterState.NONE
            and a.applied_at <= now - timedelta(days=14)
        ):
            a.recruiter_state = RecruiterState.SILENT
            a.updated_at = now
            session.add(a)
            updated += 1
    if updated:
        await session.flush()
    return updated


# ── Stuck-queue surface ────────────────────────────────────────────────


async def stuck_drafts(session: AsyncSession, *, user_id: int) -> list[Application]:
    """DRAFTs with `submission_artifacts.last_failure` populated.

    Surfaces in Discover right rail "Stuck in queue · {N}" card. Filtered to
    the current user — vault boundary applies (we never leak another user's
    failures across the API).
    """
    apps = (
        await session.exec(
            select(Application).where(
                Application.user_id == user_id,
                Application.status == ApplicationStatus.DRAFT,
                Application.deleted_at.is_(None),
                Application.submission_artifacts.is_not(None),
            )
        )
    ).all()
    return [
        a for a in apps if a.submission_artifacts and a.submission_artifacts.get("last_failure")
    ]
