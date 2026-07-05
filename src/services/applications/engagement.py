"""Computed state — referral-state roll-up + outreach engagement.

Split out of services/application_service.py in plan 91 Phase 4.2;
behaviour unchanged. Internal calls to shimmed/patched seams go through
`svc()` (the facade) so test interception keeps working.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import (
    ContactApplicationLink,
    OutreachMessage,
    OutreachStatus,
    ReferralState,
)
from services.applications.common import (
    svc,
)

log = logging.getLogger(__name__)


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
    application = await svc().get_application(session, application_id)
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


# ── Stuck-queue surface ────────────────────────────────────────────────
