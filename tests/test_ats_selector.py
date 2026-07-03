"""ATS adapter selection — `Application.board` primary signal (plan 63 § D.10).

Per plan: `Application.board` is the primary adapter-selection signal;
URL pattern is the per-adapter `can_submit(job)` tie-break (defense-in-depth
against a misaligned `Job.source` from older scraper output). The skeleton
adapters' `can_submit` returns False so the auto-apply queue skips them;
once the per-adapter PR ships, `can_submit` matches the board's URL pattern.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from models import ApplicationBoard
from services.ats import dispatch
from services.ats.ashby import AshbyAdapter
from services.ats.generic import GenericAdapter
from services.ats.greenhouse import GreenhouseAdapter
from services.ats.indeed import IndeedAdapter
from services.ats.lever import LeverAdapter
from services.ats.linkedin_apply import LinkedInAdapter
from services.ats.workday import WorkdayAdapter

pytestmark = pytest.mark.uses_sample_data_shims


@pytest.mark.parametrize(
    "board, expected_cls",
    [
        (ApplicationBoard.GREENHOUSE, GreenhouseAdapter),
        (ApplicationBoard.LEVER, LeverAdapter),
        (ApplicationBoard.ASHBY, AshbyAdapter),
        (ApplicationBoard.WORKDAY, WorkdayAdapter),
        (ApplicationBoard.LINKEDIN, LinkedInAdapter),
        (ApplicationBoard.INDEED, IndeedAdapter),
        (ApplicationBoard.COMPANY_DIRECT, GenericAdapter),
    ],
)
def test_dispatch_resolves_each_board_to_a_concrete_class(board, expected_cls):
    """7 of 8 ApplicationBoard values resolve to a concrete adapter class;
    MANUAL falls through to `_ManualFallbackAdapter` (covered separately)."""
    assert isinstance(dispatch(board), expected_cls)


def test_greenhouse_can_submit_uses_url_pattern():
    """Existing production adapter — URL pattern is the tie-break per plan § D.10."""
    job_ok = SimpleNamespace(url="https://boards.greenhouse.io/foo/jobs/1", apply_url=None)
    job_bad = SimpleNamespace(url="https://example.com/jobs/1", apply_url=None)
    assert GreenhouseAdapter().can_submit(job_ok) is True
    assert GreenhouseAdapter().can_submit(job_bad) is False


def test_skeleton_can_submit_false_for_any_url():
    """Skeleton adapters never claim to submit — auto-apply queue skips."""
    job = SimpleNamespace(url="https://workday.salesforce.com/anything", apply_url=None)
    for adapter_cls in (WorkdayAdapter, LinkedInAdapter, IndeedAdapter, GenericAdapter):
        assert adapter_cls().can_submit(job) is False
