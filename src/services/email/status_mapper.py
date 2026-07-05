"""EmailClassification → ApplicationStatus suggestion table (plan 90 / 0.5.0.03).

Pure function. Never mutates state. Returns a `SuggestedTransition` describing
what status the operator MIGHT want to flip to; the actual flip happens in
`application_service.apply_email_suggestion` when the operator clicks "Apply"
on the in-app banner. Auto-flip without consent is explicitly forbidden by
plan § A.5.b lock (human-confirm-all foundation).
"""

from __future__ import annotations

from dataclasses import dataclass

from models import Application
from models.enums import ApplicationStatus, ClosedReason, EmailClassification


@dataclass(slots=True)
class SuggestedTransition:
    current_status: ApplicationStatus
    suggested_status: ApplicationStatus
    closed_reason: ClosedReason | None = None
    reason_text: str | None = None


def suggest_status(
    application: Application,
    classification: EmailClassification,
    *,
    urgency: str | None = None,
) -> SuggestedTransition | None:
    """Return a non-destructive suggestion or None when no flip applies.

    Mapping per plan § A.5 table:

    | EmailClassification | Suggested ApplicationStatus | Closed reason | Skip when |
    |---|---|---|---|
    | INTERVIEW_REQUEST | RECRUITER_SCREEN / ONSITE_LOOP | — | already past |
    | ASSESSMENT | RECRUITER_SCREEN | — | urgency=low |
    | OFFER | OFFER | — | already OFFER/CLOSED |
    | REJECTION | CLOSED | rejected_by_them | already CLOSED/OFFER |
    | FOLLOW_UP / OTHER | — | — | always skip |
    """
    current = application.status

    if classification == EmailClassification.INTERVIEW_REQUEST:
        if current == ApplicationStatus.APPLIED:
            return SuggestedTransition(
                current_status=current,
                suggested_status=ApplicationStatus.RECRUITER_SCREEN,
                reason_text="Interview request received",
            )
        if current == ApplicationStatus.RECRUITER_SCREEN:
            return SuggestedTransition(
                current_status=current,
                suggested_status=ApplicationStatus.ONSITE_LOOP,
                reason_text="Next-round interview request received",
            )
        return None

    if classification == EmailClassification.ASSESSMENT:
        if urgency == "low":
            return None
        if current == ApplicationStatus.APPLIED:
            return SuggestedTransition(
                current_status=current,
                suggested_status=ApplicationStatus.RECRUITER_SCREEN,
                reason_text="Take-home / assessment received",
            )
        return None

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
