"""email_status_mapper — pure-function mapping table coverage.

Plan 90 / 0.5.0.03 Wave 9.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("NAAVIK_DEBUG", "1")

pytestmark = pytest.mark.uses_sample_data_shims


def _app(status):
    return SimpleNamespace(status=status)


def test_interview_request_from_applied_to_recruiter_screen():
    from models.enums import ApplicationStatus, EmailClassification
    from services.email import status_mapper as email_status_mapper

    t = email_status_mapper.suggest_status(
        _app(ApplicationStatus.APPLIED),
        EmailClassification.INTERVIEW_REQUEST,
    )
    assert t is not None
    assert t.suggested_status == ApplicationStatus.RECRUITER_SCREEN


def test_interview_request_from_recruiter_screen_to_onsite():
    from models.enums import ApplicationStatus, EmailClassification
    from services.email import status_mapper as email_status_mapper

    t = email_status_mapper.suggest_status(
        _app(ApplicationStatus.RECRUITER_SCREEN),
        EmailClassification.INTERVIEW_REQUEST,
    )
    assert t is not None
    assert t.suggested_status == ApplicationStatus.ONSITE_LOOP


def test_offer_suggests_offer():
    from models.enums import ApplicationStatus, EmailClassification
    from services.email import status_mapper as email_status_mapper

    t = email_status_mapper.suggest_status(
        _app(ApplicationStatus.RECRUITER_SCREEN),
        EmailClassification.OFFER,
    )
    assert t is not None
    assert t.suggested_status == ApplicationStatus.OFFER


def test_offer_skip_when_already_offer():
    from models.enums import ApplicationStatus, EmailClassification
    from services.email import status_mapper as email_status_mapper

    assert (
        email_status_mapper.suggest_status(_app(ApplicationStatus.OFFER), EmailClassification.OFFER)
        is None
    )


def test_rejection_suggests_closed_rejected_by_them():
    from models.enums import ApplicationStatus, ClosedReason, EmailClassification
    from services.email import status_mapper as email_status_mapper

    t = email_status_mapper.suggest_status(
        _app(ApplicationStatus.APPLIED),
        EmailClassification.REJECTION,
    )
    assert t is not None
    assert t.suggested_status == ApplicationStatus.CLOSED
    assert t.closed_reason == ClosedReason.REJECTED_BY_THEM


def test_rejection_skip_when_already_offer_or_closed():
    from models.enums import ApplicationStatus, EmailClassification
    from services.email import status_mapper as email_status_mapper

    for s in (ApplicationStatus.OFFER, ApplicationStatus.CLOSED):
        assert email_status_mapper.suggest_status(_app(s), EmailClassification.REJECTION) is None


def test_assessment_skip_when_urgency_low():
    from models.enums import ApplicationStatus, EmailClassification
    from services.email import status_mapper as email_status_mapper

    assert (
        email_status_mapper.suggest_status(
            _app(ApplicationStatus.APPLIED),
            EmailClassification.ASSESSMENT,
            urgency="low",
        )
        is None
    )


def test_follow_up_and_other_always_skip():
    from models.enums import ApplicationStatus, EmailClassification
    from services.email import status_mapper as email_status_mapper

    for c in (EmailClassification.FOLLOW_UP, EmailClassification.OTHER):
        assert email_status_mapper.suggest_status(_app(ApplicationStatus.APPLIED), c) is None


# ── Stage-aware mapping (2026-07 tracking redesign) ─────────────────────


def test_interview_request_stage_interview_jumps_to_interview_stage():
    from models.enums import ApplicationStatus, EmailClassification
    from services.email import status_mapper as email_status_mapper

    for s in (ApplicationStatus.APPLIED, ApplicationStatus.RECRUITER_SCREEN):
        t = email_status_mapper.suggest_status(
            _app(s), EmailClassification.INTERVIEW_REQUEST, stage="interview"
        )
        assert t is not None
        assert t.suggested_status == ApplicationStatus.ONSITE_LOOP


def test_interview_request_stage_screen_never_ratchets_backwards():
    """A reminder about the SAME screen must not advance the pipeline."""
    from models.enums import ApplicationStatus, EmailClassification
    from services.email import status_mapper as email_status_mapper

    for s in (ApplicationStatus.RECRUITER_SCREEN, ApplicationStatus.ONSITE_LOOP):
        assert (
            email_status_mapper.suggest_status(
                _app(s), EmailClassification.INTERVIEW_REQUEST, stage="screen"
            )
            is None
        )


def test_interview_request_stage_interview_idempotent_at_interview_stage():
    from models.enums import ApplicationStatus, EmailClassification
    from services.email import status_mapper as email_status_mapper

    assert (
        email_status_mapper.suggest_status(
            _app(ApplicationStatus.ONSITE_LOOP),
            EmailClassification.INTERVIEW_REQUEST,
            stage="interview",
        )
        is None
    )


def test_timeline_derivation_orders_signals():
    from models.enums import ApplicationStatus, ClosedReason, EmailClassification
    from services.email import status_mapper as email_status_mapper

    # screen → interview → strongest wins
    status, reason = email_status_mapper.status_for_email_timeline(
        [
            (EmailClassification.INTERVIEW_REQUEST, "screen"),
            (EmailClassification.INTERVIEW_REQUEST, "interview"),
        ]
    )
    assert status == ApplicationStatus.ONSITE_LOOP
    assert reason is None

    # offer trumps everything
    status, _ = email_status_mapper.status_for_email_timeline(
        [
            (EmailClassification.INTERVIEW_REQUEST, "interview"),
            (EmailClassification.OFFER, None),
        ]
    )
    assert status == ApplicationStatus.OFFER

    # trailing rejection closes the process
    status, reason = email_status_mapper.status_for_email_timeline(
        [
            (EmailClassification.INTERVIEW_REQUEST, "interview"),
            (EmailClassification.REJECTION, None),
        ]
    )
    assert status == ApplicationStatus.CLOSED
    assert reason == ClosedReason.REJECTED_BY_THEM

    # rejection followed by a NEW interview signal keeps the process open
    status, _ = email_status_mapper.status_for_email_timeline(
        [
            (EmailClassification.REJECTION, None),
            (EmailClassification.INTERVIEW_REQUEST, "screen"),
        ]
    )
    assert status == ApplicationStatus.RECRUITER_SCREEN
