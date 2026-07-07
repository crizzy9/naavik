"""Status-transition rules + user-driven status flips + bulk moves.

Split out of the former services/application_service.py in plan 91 Phase 4.2;
behaviour unchanged. Internal calls to shimmed/patched seams go through
`svc()` (the facade) so test interception keeps working.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlmodel.ext.asyncio.session import AsyncSession

from models import (
    AppEventKind,
    Application,
    ApplicationStatus,
    ClosedReason,
    StatusChangeTrigger,
)
from services.applications.common import (
    ApplicationServiceError,
    IllegalStateTransition,
    ValidationError,
    _emit_event,
    svc,
)

log = logging.getLogger(__name__)


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


async def update_status(
    session: AsyncSession,
    application_id: int,
    new_status: ApplicationStatus,
    *,
    closed_reason: ClosedReason | None = None,
    notes: str | None = None,
    trigger: StatusChangeTrigger = StatusChangeTrigger.MANUAL,
) -> Application:
    """User-driven (or email-confirmed) status flip.

    Plan 90 / 0.5.0.03 added the `trigger` kwarg so email-suggestion flows can
    record `AUTO_FROM_EMAIL` in the AppEvent payload while reusing the same
    transition + validation path. Default stays MANUAL so existing call sites
    are unchanged.

    Forward transitions are enforced; a backwards transition is allowed but
    logged as `MANUAL_OVERRIDE` AppEvent so audit history is preserved.
    """
    application = await svc().get_application(session, application_id)
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

    # Plan 95 § 3.8 — manual moves manage the status pin: a backward drag
    # pins the reverted status against email re-application; advancing to or
    # past the pin clears it (the objection is moot).
    if trigger == StatusChangeTrigger.MANUAL:
        from services.applications.pins import stamp_pin_on_manual_move

        stamp_pin_on_manual_move(
            application, from_status=current, to_status=new_status, is_forward=is_forward
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
            "trigger": trigger.value,
            "is_forward": is_forward,
            "notes": notes,
        },
    )
    await session.flush()
    return application


# ── Mid-stage creation with an honest trail (plan 95 §§ 3.7 / surface 5) ─


async def create_tracked_application(
    session: AsyncSession,
    *,
    user_id: int,
    job,
    status: ApplicationStatus,
    applied_at: datetime,
    closed_reason: ClosedReason | None = None,
    submission_artifacts: dict | None = None,
    actor: str,
    first_note: str,
    stage_note: str | None = None,
    stage_occurred_at: datetime | None = None,
    first_trigger: StatusChangeTrigger = StatusChangeTrigger.AUTO_FROM_EMAIL,
    stage_trigger: StatusChangeTrigger = StatusChangeTrigger.AUTO_FROM_EMAIL,
) -> Application:
    """Create an Application already mid-pipeline WITH the back-dated
    APPLIED → stage AppEvent trail, so KPI queries and the timeline see the
    same shape as an application the pipeline observed live.

    The one shared way to enter mid-stage — used by the detected-process
    "Track it" flow and the § 3.7 manual-add "Where does this stand?"
    control; a second trail-writing dialect would skew the funnel.
    """
    from models import DocsState, RecruiterState, ReferralState

    now = datetime.now(UTC)
    application = Application(
        user_id=user_id,
        job_id=job.id,
        company=job.company,
        role=job.role,
        team=job.team,
        location=job.location,
        board=job.board,
        external_url=job.url if not str(job.url).startswith("manual://") else None,
        status=status,
        closed_reason=closed_reason,
        docs_state=DocsState.NONE,
        referral_state=ReferralState.NONE,
        recruiter_state=RecruiterState.NONE,
        applied_at=applied_at,
        submission_artifacts=submission_artifacts or {},
        created_at=now,
        updated_at=now,
    )
    session.add(application)
    await session.flush()

    await _emit_event(
        session,
        user_id=user_id,
        application_id=application.id,
        kind=AppEventKind.STATUS_CHANGE,
        occurred_at=applied_at,
        actor=actor,
        payload={
            "from": None,
            "to": ApplicationStatus.APPLIED.value,
            "trigger": first_trigger.value,
            "is_forward": True,
            "notes": first_note,
        },
    )
    if status != ApplicationStatus.APPLIED:
        await _emit_event(
            session,
            user_id=user_id,
            application_id=application.id,
            kind=AppEventKind.STATUS_CHANGE,
            occurred_at=stage_occurred_at or now,
            actor=actor,
            payload={
                "from": ApplicationStatus.APPLIED.value,
                "to": status.value,
                "trigger": stage_trigger.value,
                "is_forward": status != ApplicationStatus.CLOSED,
                "notes": stage_note or first_note,
            },
        )
    await session.flush()
    return application


# ── Email-suggestion human-confirm seam (plan 90 / 0.5.0.03) ────────────


BULK_MAX_IDS = 50


async def bulk_update_status(
    session: AsyncSession,
    *,
    user_id: int,
    application_ids: list[int],
    new_status: ApplicationStatus,
    closed_reason: ClosedReason | None = None,
) -> tuple[int, list[int]]:
    """Bulk-update status. Returns ``(success_count, failed_ids)``.

    Iterates per-ID and routes through ``update_status`` so the existing
    forward-transition + closed_reason rules + AppEvent emission still fire.
    Failed IDs cover three buckets: missing application, cross-user IDOR
    (silently ignored), and `update_status` raising
    ``IllegalStateTransition`` / ``ValidationError``.

    Caps `application_ids` at ``BULK_MAX_IDS`` (50) to keep transaction
    duration bounded.
    """
    if len(application_ids) > BULK_MAX_IDS:
        raise ValidationError(
            f"Bulk operation limit is {BULK_MAX_IDS} applications per request",
            code="bulk_limit_exceeded",
        )

    success = 0
    failed: list[int] = []
    for app_id in application_ids:
        application = await svc().get_application(session, app_id)
        if application is None or application.user_id != user_id:
            failed.append(app_id)
            continue
        try:
            await svc().update_status(
                session,
                app_id,
                new_status,
                closed_reason=closed_reason,
            )
            success += 1
        except (IllegalStateTransition, ValidationError):
            failed.append(app_id)
    return success, failed


async def bulk_archive(
    session: AsyncSession,
    *,
    user_id: int,
    application_ids: list[int],
) -> tuple[int, list[int]]:
    """Bulk archive: status=CLOSED, closed_reason=USER_ARCHIVED.

    Wraps ``bulk_update_status`` with the USER_ARCHIVED reason so the
    audit-event payload distinguishes operator-initiated archive from
    rejection / withdrawal / ghosting.
    """
    return await bulk_update_status(
        session,
        user_id=user_id,
        application_ids=application_ids,
        new_status=ApplicationStatus.CLOSED,
        closed_reason=ClosedReason.USER_ARCHIVED,
    )
