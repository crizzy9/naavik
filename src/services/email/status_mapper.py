"""EmailClassification → ApplicationStatus suggestion table (plan 90 / 0.5.0.03).

Pure function. Never mutates state. Returns a `SuggestedTransition` describing
the status flip an email implies. Since the 2026-07 tracking redesign,
forward (non-terminal) transitions are applied automatically by the classifier
(`trigger=AUTO_FROM_EMAIL`); REJECTION → CLOSED remains a human-confirm
suggestion so a misclassified email can never kill a live application.

Stage-aware since 2026-07: the classifier extracts an interview `stage`
("screen" | "interview") so a repeated reminder about the SAME interview no
longer ratchets the application forward one rung per email — the target rung
is derived from the stage, and equal-or-backward moves return None.
"""

from __future__ import annotations

from dataclasses import dataclass

from models import Application
from models.enums import ApplicationStatus, ClosedReason, EmailClassification

# Pipeline rank used for the forward-only guard. CLOSED deliberately absent —
# terminal moves are handled per-classification below.
_RANK: dict[ApplicationStatus, int] = {
    ApplicationStatus.DRAFT: 0,
    ApplicationStatus.APPLIED: 1,
    ApplicationStatus.RECRUITER_SCREEN: 2,
    ApplicationStatus.ONSITE_LOOP: 3,
    ApplicationStatus.OFFER: 4,
}


@dataclass(slots=True)
class SuggestedTransition:
    current_status: ApplicationStatus
    suggested_status: ApplicationStatus
    closed_reason: ClosedReason | None = None
    reason_text: str | None = None


def _forward(
    current: ApplicationStatus,
    target: ApplicationStatus,
    reason: str,
) -> SuggestedTransition | None:
    """Return the transition only when it moves the pipeline forward."""
    if current not in _RANK or _RANK[target] <= _RANK[current]:
        return None
    return SuggestedTransition(
        current_status=current,
        suggested_status=target,
        reason_text=reason,
    )


def suggest_status(
    application: Application,
    classification: EmailClassification,
    *,
    urgency: str | None = None,
    stage: str | None = None,
) -> SuggestedTransition | None:
    """Return a non-destructive suggestion or None when no flip applies.

    | EmailClassification | Target status | Closed reason | Skip when |
    |---|---|---|---|
    | INTERVIEW_REQUEST stage=screen | RECRUITER_SCREEN | — | already there/past |
    | INTERVIEW_REQUEST stage=interview | ONSITE_LOOP (Interview Stage) | — | already there/past |
    | INTERVIEW_REQUEST stage=? | one rung forward (legacy ladder) | — | already ONSITE_LOOP+ |
    | ASSESSMENT | RECRUITER_SCREEN | — | urgency=low or already past |
    | OFFER | OFFER | — | already OFFER/CLOSED |
    | REJECTION | CLOSED | rejected_by_them | already CLOSED/OFFER |
    | FOLLOW_UP / OTHER | — | — | always skip |
    """
    current = application.status

    if classification == EmailClassification.INTERVIEW_REQUEST:
        if current == ApplicationStatus.CLOSED:
            return None
        if stage == "screen":
            return _forward(
                current, ApplicationStatus.RECRUITER_SCREEN, "Recruiter screen scheduled"
            )
        if stage == "interview":
            return _forward(current, ApplicationStatus.ONSITE_LOOP, "Interview stage reached")
        # Unknown stage: conservative one-rung ladder (plan 90 behaviour).
        if current == ApplicationStatus.APPLIED:
            return _forward(
                current, ApplicationStatus.RECRUITER_SCREEN, "Interview request received"
            )
        if current == ApplicationStatus.RECRUITER_SCREEN:
            return _forward(
                current, ApplicationStatus.ONSITE_LOOP, "Next-round interview request received"
            )
        return None

    if classification == EmailClassification.ASSESSMENT:
        if urgency == "low" or current == ApplicationStatus.CLOSED:
            return None
        return _forward(
            current, ApplicationStatus.RECRUITER_SCREEN, "Take-home / assessment received"
        )

    if classification == EmailClassification.OFFER:
        if current in {ApplicationStatus.OFFER, ApplicationStatus.CLOSED}:
            return None
        return SuggestedTransition(
            current_status=current,
            suggested_status=ApplicationStatus.OFFER,
            reason_text="Offer received",
        )

    if classification == EmailClassification.REJECTION:
        if current in {ApplicationStatus.CLOSED, ApplicationStatus.OFFER}:
            return None
        return SuggestedTransition(
            current_status=current,
            suggested_status=ApplicationStatus.CLOSED,
            closed_reason=ClosedReason.REJECTED_BY_THEM,
            reason_text="Rejection received",
        )

    return None


def status_for_email_timeline(
    classifications: list[tuple[EmailClassification, str | None]],
) -> tuple[ApplicationStatus, ClosedReason | None]:
    """Derive the pipeline stage a detected (untracked) process has reached.

    Input: (classification, stage) pairs across every email mapped to one
    company, oldest first. The strongest signal wins: OFFER > interview >
    screen/assessment > receipt-only; a REJECTION closes the process unless a
    LATER positive signal shows it moved on (e.g. rejected for one role,
    interviewing for another).
    """
    best = ApplicationStatus.APPLIED
    rejected = False
    for classification, stage in classifications:
        if classification == EmailClassification.OFFER:
            return ApplicationStatus.OFFER, None
        if classification == EmailClassification.REJECTION:
            rejected = True
        elif classification == EmailClassification.INTERVIEW_REQUEST:
            rejected = False
            target = (
                ApplicationStatus.ONSITE_LOOP
                if stage == "interview"
                else ApplicationStatus.RECRUITER_SCREEN
            )
            if _RANK[target] > _RANK[best]:
                best = target
        elif classification == EmailClassification.ASSESSMENT:
            rejected = False
            if _RANK[ApplicationStatus.RECRUITER_SCREEN] > _RANK[best]:
                best = ApplicationStatus.RECRUITER_SCREEN
    if rejected:
        return ApplicationStatus.CLOSED, ClosedReason.REJECTED_BY_THEM
    return best, None
