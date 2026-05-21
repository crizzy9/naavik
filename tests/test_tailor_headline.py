"""TailoredHeadline validators + recruiter_optimization gate — plan 66 § T7."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from llm.prompts.tailor_headline import (
    MAX_CHUNK_CHARS,
    MAX_HEADLINE_CHARS,
    TailoredHeadline,
)


def test_tailored_headline_clamps_total_length():
    """Overly-long headline_one_line is truncated with ellipsis."""
    long_str = "x" * (MAX_HEADLINE_CHARS + 50)
    headline = TailoredHeadline(
        title="Senior Engineer",
        years=8,
        specialty="ML Platform",
        sponsorship_signal=None,
        headline_one_line=long_str,
    )
    assert len(headline.headline_one_line) <= MAX_HEADLINE_CHARS
    assert headline.headline_one_line.endswith("…")


def test_tailored_headline_accepts_h1b_sponsorship_signal():
    headline = TailoredHeadline(
        title="ML Engineer",
        years=8,
        specialty="ML Platform",
        sponsorship_signal="H1B+i-140",
        headline_one_line="ML Engineer · 8 yrs · ML Platform · H1B+i-140",
    )
    assert headline.sponsorship_signal == "H1B+i-140"


def test_tailored_headline_chunk_caps():
    """Per-chunk fields cap at MAX_CHUNK_CHARS."""
    too_long_title = "x" * (MAX_CHUNK_CHARS + 10)
    with pytest.raises(ValueError):  # Pydantic raises ValidationError (subclasses ValueError)
        TailoredHeadline(
            title=too_long_title,
            years=8,
            specialty="ML",
            headline_one_line="ok",
        )


def test_tailored_headline_years_bounds():
    with pytest.raises(ValueError):
        TailoredHeadline(
            title="Eng",
            years=51,  # > 50
            specialty="ML",
            headline_one_line="ok",
        )
    with pytest.raises(ValueError):
        TailoredHeadline(
            title="Eng",
            years=-1,
            specialty="ML",
            headline_one_line="ok",
        )


@pytest.mark.asyncio
async def test_tailor_headline_for_application_gates_below_threshold():
    """Below `HEADLINE_SCORE_GATE` (0.50) returns None without LLM call."""
    from services.recruiter_optimization import (
        HEADLINE_SCORE_GATE,
        tailor_headline_for_application,
    )

    session = AsyncMock()
    profile = SimpleNamespace(
        full_name="Test",
        headline="Engineer",
        summary_full="",
        summary_short="",
        work_authorization=None,
    )
    job = SimpleNamespace(
        role="Senior Engineer",
        company="Acme",
        description="Build things",
        description_html=None,
    )
    settings = SimpleNamespace(llm_provider="anthropic", llm_model="claude-3.5")

    # job_score below gate
    with patch("services.recruiter_optimization.get_provider") as mock_provider:
        result = await tailor_headline_for_application(
            session=session,
            user_id=1,
            settings=settings,
            profile=profile,
            experiences=[],
            job=job,
            job_score=HEADLINE_SCORE_GATE - 0.01,
            matched_tags=["backend"],
        )
        assert result is None
        mock_provider.assert_not_called()


def test_years_from_experiences_handles_active_role():
    """Active role (end_date=None) is treated as ending now."""
    from services.recruiter_optimization import _years_from_experiences

    start = datetime(2018, 7, 1, tzinfo=UTC)
    exp = SimpleNamespace(start_date=start, end_date=None)
    years = _years_from_experiences([exp])
    # 2026-05 - 2018-07 ≈ 7.8 years → 7 truncated.
    assert years >= 7


def test_years_from_experiences_returns_zero_for_empty():
    from services.recruiter_optimization import _years_from_experiences

    assert _years_from_experiences([]) == 0


def test_wants_sponsorship_signal():
    from models.enums import WorkAuthorization
    from services.recruiter_optimization import _wants_sponsorship_signal

    p_h1b = SimpleNamespace(work_authorization=WorkAuthorization.H1B)
    p_gc = SimpleNamespace(work_authorization=WorkAuthorization.GREEN_CARD)
    p_none = SimpleNamespace(work_authorization=None)
    assert _wants_sponsorship_signal(p_h1b)
    assert not _wants_sponsorship_signal(p_gc)
    assert not _wants_sponsorship_signal(p_none)
