"""Wave 6 — scorer visa filter tests.

Per plan 10 § C.1. The deterministic filter zero-outs jobs that require
US citizenship or a Green Card whenever the candidate needs sponsorship.
The LLM `score_job` call is unaffected — the filter wraps its output.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from llm.prompts.score_job import JobScore
from models import VisaSponsorship
from services.scorer import apply_visa_filter, needs_visa_zero_out

pytestmark = pytest.mark.uses_sample_data_shims


def _profile(visa: VisaSponsorship | None):
    return SimpleNamespace(visa_sponsorship_needed=visa)


def _job(restrictions: str | None):
    return SimpleNamespace(visa_restrictions=restrictions)


def test_needs_visa_zero_out_us_citizen_only():
    p = _profile(VisaSponsorship.NEEDED_NOW)
    j = _job("us_citizen_only")
    assert needs_visa_zero_out(p, j) is True


def test_needs_visa_zero_out_green_card_required():
    p = _profile(VisaSponsorship.NEEDED_NOW)
    j = _job("green_card_required")
    assert needs_visa_zero_out(p, j) is True


def test_no_zero_out_when_candidate_doesnt_need_sponsorship():
    p = _profile(VisaSponsorship.NOT_NEEDED)
    j = _job("us_citizen_only")
    assert needs_visa_zero_out(p, j) is False


def test_no_zero_out_when_job_has_no_restriction():
    p = _profile(VisaSponsorship.NEEDED_NOW)
    j = _job(None)
    assert needs_visa_zero_out(p, j) is False


def test_no_zero_out_when_restriction_unknown_value():
    p = _profile(VisaSponsorship.NEEDED_NOW)
    j = _job("any_authorized")
    assert needs_visa_zero_out(p, j) is False


def test_apply_visa_filter_zeroes_blocked_job():
    p = _profile(VisaSponsorship.NEEDED_NOW)
    j = _job("us_citizen_only")
    raw = JobScore(score=0.92, explanation="great fit", matched_tags=["backend"])
    out = apply_visa_filter(raw, p, j)
    assert out.score == 0.0
    assert out.visa_concern is True
    assert out.matched_tags == ["backend"]


def test_apply_visa_filter_passthrough_when_safe():
    p = _profile(VisaSponsorship.NOT_NEEDED)
    j = _job(None)
    raw = JobScore(score=0.85, explanation="fit", matched_tags=[])
    out = apply_visa_filter(raw, p, j)
    assert out.score == 0.85
    assert out.visa_concern is False


def test_apply_visa_filter_handles_uppercase_restriction():
    p = _profile(VisaSponsorship.NEEDED_NOW)
    j = _job("US_CITIZEN_ONLY")
    raw = JobScore(score=0.7, explanation="x", matched_tags=[])
    out = apply_visa_filter(raw, p, j)
    assert out.score == 0.0


def test_apply_visa_filter_returns_new_object_not_mutated():
    p = _profile(VisaSponsorship.NEEDED_NOW)
    j = _job("us_citizen_only")
    raw = JobScore(score=0.99, explanation="amazing", matched_tags=["backend"])
    out = apply_visa_filter(raw, p, j)
    assert out is not raw
    assert raw.score == 0.99  # original unchanged
