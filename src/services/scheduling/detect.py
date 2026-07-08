"""Scheduling-need detection — plan 96 slice 96f.

Two detectors feed the "Needs scheduling" strip:

1. **Per-message**: the classifier's `action_needed` extraction, gated by
   the deterministic keyword post-check below (the `end_client` pattern —
   the model can't claim an ask the text never makes).
2. **Per-conversation**: the reconciler's `needs_scheduling` stamp in
   `submission_artifacts["reconcile"]` (96e) — the conversation-coherent
   read that catches asks spread across messages.

Detection only — nothing here writes state, sends mail, or touches a
network.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import Application, EmailMessage
from models.enums import ApplicationStatus, EmailClassification

ACTION_NEEDED_VOCAB = ("none", "send_availability", "pick_slot", "confirm_time")

# The label must be corroborated by at least one keyword in the text the
# model saw, or it degrades to None — mirrors the end_client verbatim check.
_ACTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "send_availability": (
        "availability",
        "available",
        "times that work",
        "time that works",
        "few times",
        "best time",
        "what times",
        "days/times",
    ),
    "pick_slot": (
        "book",
        "booking",
        "calendly",
        "goodtime",
        "schedule here",
        "scheduling link",
        "pick a time",
        "choose a time",
        "select a time",
        "grab a time",
        "following link",
        "self-schedule",
        "reschedule",
        "schedule your",
        "sign up",
        "slots",
    ),
    "confirm_time": (
        "confirm",
        "does this work",
        "work for you",
        "sound good",
        "let me know if",
    ),
}

_ACTIVE_STATUSES = (
    ApplicationStatus.APPLIED,
    ApplicationStatus.RECRUITER_SCREEN,
    ApplicationStatus.ONSITE_LOOP,
    ApplicationStatus.OFFER,
)

ACTION_LABELS = {
    "send_availability": "send availability",
    "pick_slot": "pick a slot",
    "confirm_time": "confirm a time",
}


def action_needed_post_check(label: str | None, *, text: str) -> str | None:
    """Deterministic gate on the classifier's `action_needed` guess."""
    cleaned = (label or "").strip().lower() or None
    if cleaned in (None, "none"):
        return None
    if cleaned not in ACTION_NEEDED_VOCAB:
        return None
    haystack = text.lower()
    if any(keyword in haystack for keyword in _ACTION_KEYWORDS.get(cleaned, ())):
        return cleaned
    return None


@dataclass(slots=True)
class NeedsScheduling:
    application_id: int
    company: str
    role: str | None
    action: str  # vocabulary key, or "needs_scheduling" (conversation-level)
    action_label: str
    subject: str
    message_id: int | None  # the evidence message (reply target), if any
    detected_at: datetime | None
    urgency: str | None


async def list_needs_scheduling(session: AsyncSession, *, user_id: int) -> list[NeedsScheduling]:
    """One row per live application whose ball is in the owner's court.

    A message-level detection counts only while it is the LAST word in its
    thread (a later message means the conversation moved on). Urgency-first,
    then recency (§ 5.6: the strip is urgency-ordered).
    """
    applications = (
        await session.exec(
            select(Application).where(
                Application.user_id == user_id,
                Application.deleted_at.is_(None),  # type: ignore[union-attr]
                Application.status.in_(_ACTIVE_STATUSES),  # type: ignore[union-attr]
            )
        )
    ).all()
    if not applications:
        return []
    app_ids = [a.id for a in applications if a.id is not None]
    flagged = (
        await session.exec(
            select(EmailMessage)
            .where(
                EmailMessage.application_id.in_(app_ids),  # type: ignore[union-attr]
                EmailMessage.action_needed.is_not(None),  # type: ignore[union-attr]
                EmailMessage.action_needed != "none",
            )
            .order_by(EmailMessage.received_at.desc())
        )
    ).all()

    out: dict[int, NeedsScheduling] = {}
    for msg in flagged:
        if msg.application_id in out:
            continue
        latest_in_thread = (
            await session.exec(
                select(EmailMessage.id)
                .where(EmailMessage.thread_id == msg.thread_id)
                .order_by(EmailMessage.received_at.desc())
                .limit(1)
            )
        ).first()
        if latest_in_thread != msg.id:
            continue  # the conversation moved past the ask
        application = next((a for a in applications if a.id == msg.application_id), None)
        if application is None:
            continue
        out[application.id or 0] = NeedsScheduling(
            application_id=application.id or 0,
            company=application.company,
            role=application.role,
            action=msg.action_needed or "none",
            action_label=ACTION_LABELS.get(msg.action_needed or "", "scheduling"),
            subject=msg.subject,
            message_id=msg.id,
            detected_at=msg.received_at,
            urgency=msg.urgency,
        )

    # Conversation-level stamps from the reconciler (96e) fill the gaps.
    for application in applications:
        if application.id in out:
            continue
        stamp = ((application.submission_artifacts or {}).get("reconcile") or {}).get(
            "needs_scheduling"
        )
        if not isinstance(stamp, dict):
            continue
        anchor = await _newest_signal_message(session, application_id=application.id or 0)
        out[application.id or 0] = NeedsScheduling(
            application_id=application.id or 0,
            company=application.company,
            role=application.role,
            action="needs_scheduling",
            action_label="scheduling",
            subject=str(stamp.get("subject") or (anchor.subject if anchor else ""))[:120],
            message_id=anchor.id if anchor else None,
            detected_at=anchor.received_at if anchor else None,
            urgency=anchor.urgency if anchor else None,
        )

    urgency_rank = {"high": 0, "medium": 1, "low": 2, None: 3}
    return sorted(
        out.values(),
        key=lambda n: (
            urgency_rank.get(n.urgency, 3),
            -(n.detected_at.timestamp() if n.detected_at else 0.0),
        ),
    )


async def _newest_signal_message(
    session: AsyncSession, *, application_id: int
) -> EmailMessage | None:
    return (
        await session.exec(
            select(EmailMessage)
            .where(
                EmailMessage.application_id == application_id,
                EmailMessage.classification.in_(  # type: ignore[union-attr]
                    [
                        EmailClassification.INTERVIEW_REQUEST,
                        EmailClassification.ASSESSMENT,
                        EmailClassification.FOLLOW_UP,
                    ]
                ),
            )
            .order_by(EmailMessage.received_at.desc())
            .limit(1)
        )
    ).first()
