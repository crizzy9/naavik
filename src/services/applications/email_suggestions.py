"""Email-suggestion human-confirm seam (plan 90 / 0.5.0.03).

Split out of the former services/application_service.py in plan 91 Phase 4.2;
behaviour unchanged. Internal calls to shimmed/patched seams go through
`svc()` (the facade) so test interception keeps working.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import (
    Application,
    ApplicationStatus,
    ClosedReason,
    ReferralState,
    StatusChangeTrigger,
)
from services.applications.common import (
    ApplicationServiceError,
    ValidationError,
    svc,
)

log = logging.getLogger(__name__)


async def apply_email_suggestion(
    session: AsyncSession,
    *,
    application_id: int,
    message_id: int,
    user_id: int,
) -> Application:
    """Apply the pending email-classification suggestion onto the Application.

    IDOR-guarded — verifies the suggesting EmailMessage belongs to `user_id`
    AND targets `application_id`. Raises ApplicationServiceError on any
    mismatch (mapped to 404 by the route handler).
    """
    from models import EmailMessage

    msg = (
        await session.exec(
            select(EmailMessage).where(
                EmailMessage.id == message_id,
                EmailMessage.user_id == user_id,
                EmailMessage.application_id == application_id,
            )
        )
    ).one_or_none()
    if msg is None:
        raise ApplicationServiceError("suggestion not found")
    if msg.suggested_status is None:
        raise ValidationError(
            "no pending suggestion",
            code="suggestion_missing",
        )
    if msg.suggestion_applied_at is not None or msg.suggestion_dismissed_at is not None:
        raise ValidationError(
            "suggestion already resolved",
            code="suggestion_already_resolved",
        )

    suggested = msg.suggested_status
    closed_reason: ClosedReason | None = None
    if suggested == ApplicationStatus.CLOSED:
        closed_reason = ClosedReason.REJECTED_BY_THEM

    application = await svc().update_status(
        session,
        application_id,
        suggested,
        closed_reason=closed_reason,
        trigger=StatusChangeTrigger.AUTO_FROM_EMAIL,
    )

    now = datetime.now(UTC)
    msg.suggestion_applied_at = now
    session.add(msg)
    await session.flush()

    # Plan 96e — accepting a suggestion is new information: re-derive the
    # application (rounds/invites may have context the applied flip didn't).
    from services.email import reconcile as reconcile_service

    try:
        await reconcile_service.reconcile_application(
            session, application_id=application_id, triggering_thread_ids={msg.thread_id}
        )
    except Exception as exc:  # noqa: BLE001 — the applied flip must survive
        log.warning("post-suggestion reconcile failed for application %s: %s", application_id, exc)
    return application


async def dismiss_email_suggestion(
    session: AsyncSession,
    *,
    application_id: int,
    message_id: int,
    user_id: int,
) -> None:
    """Mark a pending email suggestion as dismissed by the operator."""
    from models import EmailMessage

    msg = (
        await session.exec(
            select(EmailMessage).where(
                EmailMessage.id == message_id,
                EmailMessage.user_id == user_id,
                EmailMessage.application_id == application_id,
            )
        )
    ).one_or_none()
    if msg is None:
        raise ApplicationServiceError("suggestion not found")
    if msg.suggestion_applied_at is not None or msg.suggestion_dismissed_at is not None:
        raise ValidationError(
            "suggestion already resolved",
            code="suggestion_already_resolved",
        )
    msg.suggestion_dismissed_at = datetime.now(UTC)
    session.add(msg)
    await session.flush()


# ── Computed state — referral + outreach ────────────────────────────────


_REFERRAL_PRIORITY = {
    ReferralState.PROVIDED: 4,
    ReferralState.IN_FLIGHT: 3,
    ReferralState.REQUESTED: 2,
    ReferralState.DECLINED: 1,
    ReferralState.NONE: 0,
}
