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
    from services import email_status_mapper

    t = email_status_mapper.suggest_status(
        _app(ApplicationStatus.APPLIED),
        EmailClassification.INTERVIEW_REQUEST,
    )
    assert t is not None
    assert t.suggested_status == ApplicationStatus.RECRUITER_SCREEN


def test_interview_request_from_recruiter_screen_to_onsite():
    from models.enums import ApplicationStatus, EmailClassification
    from services import email_status_mapper

    t = email_status_mapper.suggest_status(
        _app(ApplicationStatus.RECRUITER_SCREEN),
        EmailClassification.INTERVIEW_REQUEST,
    )
    assert t is not None
    assert t.suggested_status == ApplicationStatus.ONSITE_LOOP


def test_offer_suggests_offer():
    from models.enums import ApplicationStatus, EmailClassification
    from services import email_status_mapper

    t = email_status_mapper.suggest_status(
        _app(ApplicationStatus.RECRUITER_SCREEN),
        EmailClassification.OFFER,
    )
    assert t is not None
    assert t.suggested_status == ApplicationStatus.OFFER


def test_offer_skip_when_already_offer():
    from models.enums import ApplicationStatus, EmailClassification
    from services import email_status_mapper

    assert (
        email_status_mapper.suggest_status(_app(ApplicationStatus.OFFER), EmailClassification.OFFER)
        is None
    )


def test_rejection_suggests_closed_rejected_by_them():
    from models.enums import ApplicationStatus, ClosedReason, EmailClassification
    from services import email_status_mapper

    t = email_status_mapper.suggest_status(
        _app(ApplicationStatus.APPLIED),
        EmailClassification.REJECTION,
    )
    assert t is not None
    assert t.suggested_status == ApplicationStatus.CLOSED
    assert t.closed_reason == ClosedReason.REJECTED_BY_THEM


def test_rejection_skip_when_already_offer_or_closed():
    from models.enums import ApplicationStatus, EmailClassification
    from services import email_status_mapper

    for s in (ApplicationStatus.OFFER, ApplicationStatus.CLOSED):
        assert email_status_mapper.suggest_status(_app(s), EmailClassification.REJECTION) is None


def test_assessment_skip_when_urgency_low():
    from models.enums import ApplicationStatus, EmailClassification
    from services import email_status_mapper

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
    from services import email_status_mapper

    for c in (EmailClassification.FOLLOW_UP, EmailClassification.OTHER):
        assert email_status_mapper.suggest_status(_app(ApplicationStatus.APPLIED), c) is None
