"""Manual-over-email precedence — the status pin (plan 95 § 3.8, slice 95h).

Provenance-aware precedence, per-decision rather than per-application:

- Rule 2: a BACKWARD manual move pins the status the human reverted — the
  email pipeline will not re-apply a transition to that same status; it
  downgrades to a suggestion.
- Rule 3: forward manual moves don't block better news — an OFFER email
  still auto-applies (strictly forward, uncontradicted).
- Rule 4: CLOSED is absolute — a closed application never receives auto
  transitions, only suggestions; reopening is a human act.
- Rule 5: every suppressed transition still emits EMAIL_STATUS_SUGGESTED
  (`applied: false`) — the system explains itself instead of going quiet.
- Rule 6: unpinning is first-class — "Resume auto-tracking" chip, "Apply &
  resume" on the suggestion, and auto-clear when the human advances to or
  past the pinned status.

The pin lives in `submission_artifacts["status_pin"]` (JSONB slot — no
migration): `{"rejected": "<STATUS>", "at": "<iso>"}`.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlmodel.ext.asyncio.session import AsyncSession

from models import Application
from models.enums import ApplicationStatus

log = logging.getLogger(__name__)

PIN_KEY = "status_pin"

_RANK = {
    ApplicationStatus.DRAFT: 0,
    ApplicationStatus.APPLIED: 1,
    ApplicationStatus.RECRUITER_SCREEN: 2,
    ApplicationStatus.ONSITE_LOOP: 3,
    ApplicationStatus.OFFER: 4,
}


class PinError(Exception):
    """Ownership / lookup failure — routes map this to 404."""


def get_status_pin(application: Application) -> dict | None:
    pin = (application.submission_artifacts or {}).get(PIN_KEY)
    return pin if isinstance(pin, dict) and pin.get("rejected") else None


def auto_transition_allowed(application: Application, suggested: ApplicationStatus) -> bool:
    """The § 3.8 policy read, called by the email-transition path."""
    if application.status == ApplicationStatus.CLOSED:
        return False  # rule 4 — closed is absolute; reopening is a human act
    pin = get_status_pin(application)
    # Rule 2 blocks the humanly-rejected status; rule 3 lets everything
    # else (uncontradicted forward news) flow.
    return not (pin is not None and pin.get("rejected") == suggested.value)


def stamp_pin_on_manual_move(
    application: Application,
    *,
    from_status: ApplicationStatus,
    to_status: ApplicationStatus,
    is_forward: bool,
) -> None:
    """Called inside `update_status` for MANUAL triggers (mutates in place;
    caller persists). Backward move → pin the reverted status; a manual move
    to-or-past the pinned status → the objection is moot, clear it."""
    artifacts = dict(application.submission_artifacts or {})
    if (
        not is_forward
        and from_status != to_status
        and to_status != ApplicationStatus.CLOSED
        and from_status in _RANK
    ):
        artifacts[PIN_KEY] = {
            "rejected": from_status.value,
            "at": datetime.now(UTC).isoformat(),
        }
        application.submission_artifacts = artifacts
        log.info("status pin: application %s rejected=%s", application.id, from_status.value)
        return
    pin = artifacts.get(PIN_KEY)
    if not isinstance(pin, dict):
        return
    rejected_raw = pin.get("rejected")
    try:
        rejected = ApplicationStatus(rejected_raw)
    except (ValueError, TypeError):
        artifacts.pop(PIN_KEY, None)
        application.submission_artifacts = artifacts
        return
    if to_status in _RANK and rejected in _RANK and _RANK[to_status] >= _RANK[rejected]:
        artifacts.pop(PIN_KEY, None)
        application.submission_artifacts = artifacts
        log.info("status pin auto-cleared: application %s advanced past pin", application.id)


async def clear_pin(session: AsyncSession, *, user_id: int, application_id: int) -> Application:
    """ "Resume auto-tracking" — the explicit unpin affordance (rule 6)."""
    application = await session.get(Application, application_id)
    if application is None or application.user_id != user_id:
        raise PinError("No such application")
    artifacts = dict(application.submission_artifacts or {})
    artifacts.pop(PIN_KEY, None)
    application.submission_artifacts = artifacts
    application.updated_at = datetime.now(UTC)
    session.add(application)
    await session.flush()
    return application
