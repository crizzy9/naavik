"""Critique council tests — plan 67 (0.3.4) § C.3 / T14.

Covers difflib consensus detection, disagreement classification, regen
trigger (>= 2/3 revise), majority tally, and degraded-mode when every
persona fails.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from services.critique_council import (
    CONSENSUS_SIMILARITY_THRESHOLD,
    CritiqueReport,
    _cluster_concerns,
    _majority_recommendation,
    critique_bundle,
)

pytestmark = pytest.mark.uses_sample_data_shims


def _settings():
    return SimpleNamespace(
        user_id=1,
        llm_provider="anthropic",
        llm_model="claude-3.5-sonnet-20250219",
        originality_api_key=None,
    )


def test_consensus_two_personas_say_same_thing_via_similarity():
    """Two personas saying 'lacks quantification' vs 'needs more numbers'
    should NOT cluster (lexically different) — verify default behavior."""
    votes = [
        {"persona": "faang_l5_l6_hm", "concerns": ["lacks quantification"]},
        {"persona": "startup_founder", "concerns": ["lacks quantification"]},
        {"persona": "fortune_500_hr", "concerns": ["other thing"]},
    ]
    consensus, disagreement = _cluster_concerns(votes)
    assert "lacks quantification" in consensus
    assert "other thing" in disagreement


def test_consensus_lexically_similar_concerns_cluster():
    """Two phrasings sharing significant substring cluster into one consensus."""
    votes = [
        {"persona": "faang_l5_l6_hm", "concerns": ["weak quantification overall"]},
        {"persona": "startup_founder", "concerns": ["weak quantification overall here"]},
        {"persona": "fortune_500_hr", "concerns": ["nothing else"]},
    ]
    consensus, disagreement = _cluster_concerns(votes)
    assert len(consensus) == 1
    # Longest representative wins
    assert "weak quantification overall here" in consensus
    assert "nothing else" in disagreement


def test_consensus_single_persona_only_is_disagreement():
    """A concern raised by only one persona never reaches consensus.

    Uses lexically-distinct phrases so the difflib SequenceMatcher does
    NOT cluster them — verifies the "single-persona" branch of the
    consensus algorithm.
    """
    votes = [
        {"persona": "faang_l5_l6_hm", "concerns": ["lacks numbers"]},
        {"persona": "startup_founder", "concerns": ["voice too generic"]},
        {"persona": "fortune_500_hr", "concerns": ["formatting issues"]},
    ]
    consensus, disagreement = _cluster_concerns(votes)
    assert consensus == []
    assert len(disagreement) == 3


def test_consensus_empty_input_is_empty_output():
    consensus, disagreement = _cluster_concerns([])
    assert consensus == []
    assert disagreement == []


def test_consensus_three_personas_unanimous():
    votes = [
        {"persona": "faang_l5_l6_hm", "concerns": ["weak quant"]},
        {"persona": "startup_founder", "concerns": ["weak quant"]},
        {"persona": "fortune_500_hr", "concerns": ["weak quant"]},
    ]
    consensus, _ = _cluster_concerns(votes)
    assert "weak quant" in consensus


def test_majority_ship_when_2_of_3_ship():
    votes = [
        {"recommendation": "ship"},
        {"recommendation": "ship"},
        {"recommendation": "revise"},
    ]
    majority, tally = _majority_recommendation(votes)
    assert majority == "ship"
    assert tally == {"ship": 2, "revise": 1, "reject": 0}


def test_majority_revise_when_2_of_3_revise():
    votes = [
        {"recommendation": "revise"},
        {"recommendation": "revise"},
        {"recommendation": "ship"},
    ]
    majority, tally = _majority_recommendation(votes)
    assert majority == "revise"


def test_majority_tie_breaks_to_ship():
    votes = [
        {"recommendation": "ship"},
        {"recommendation": "revise"},
        {"recommendation": "reject"},
    ]
    majority, tally = _majority_recommendation(votes)
    assert majority == "ship"


@pytest.mark.asyncio
async def test_critique_bundle_majority_revise_triggers_regen():
    """When >= 2/3 personas vote revise, should_regenerate=True."""
    from llm.anthropic import BatchResponse

    settings = _settings()
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda r: None

    responses = [
        BatchResponse(
            custom_id="faang_l5_l6_hm",
            value={
                "persona": "faang_l5_l6_hm",
                "strengths": ["clear scope"],
                "concerns": ["lacks numbers"],
                "recommendation": "revise",
                "specific_changes": ["add metrics"],
            },
            input_tokens=100,
            output_tokens=50,
            succeeded=True,
        ),
        BatchResponse(
            custom_id="startup_founder",
            value={
                "persona": "startup_founder",
                "strengths": ["voice"],
                "concerns": ["lacks numbers"],
                "recommendation": "revise",
                "specific_changes": [],
            },
            input_tokens=100,
            output_tokens=50,
            succeeded=True,
        ),
        BatchResponse(
            custom_id="fortune_500_hr",
            value={
                "persona": "fortune_500_hr",
                "strengths": ["clean parse"],
                "concerns": [],
                "recommendation": "ship",
                "specific_changes": [],
            },
            input_tokens=100,
            output_tokens=50,
            succeeded=True,
        ),
    ]

    fake_provider = SimpleNamespace(
        provider_id="anthropic",
        model_name="claude-3.5-sonnet-20250219",
        estimate_cost=lambda *, input_tokens, output_tokens: 0.001,
        batch=AsyncMock(return_value=responses),
    )

    with (
        patch("services.critique_council.get_provider", return_value=fake_provider),
        patch("services.critique_council.isinstance", return_value=True),
        patch("services.critique_council._persist_apiusage", AsyncMock()),
    ):
        report = await critique_bundle(
            resume_text="resume text here",
            cover_letter_text="cover letter text",
            job_desc="job description",
            session=session,
            user_id=1,
            settings=settings,
        )

    assert isinstance(report, CritiqueReport)
    assert report.should_regenerate is True
    assert report.majority_recommendation == "revise"
    assert report.recommendation_tally["revise"] == 2
    assert report.recommendation_tally["ship"] == 1
    assert "lacks numbers" in report.consensus_concerns


@pytest.mark.asyncio
async def test_critique_bundle_unanimous_ship_no_regen():
    """3-of-3 ship → should_regenerate=False, consensus_concerns empty."""
    from llm.anthropic import BatchResponse

    settings = _settings()
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda r: None

    responses = [
        BatchResponse(
            custom_id=persona,
            value={
                "persona": persona,
                "strengths": ["x"],
                "concerns": [],
                "recommendation": "ship",
                "specific_changes": [],
            },
            input_tokens=100,
            output_tokens=50,
            succeeded=True,
        )
        for persona in ("faang_l5_l6_hm", "startup_founder", "fortune_500_hr")
    ]

    fake_provider = SimpleNamespace(
        provider_id="anthropic",
        model_name="claude-3.5-sonnet-20250219",
        estimate_cost=lambda *, input_tokens, output_tokens: 0.001,
        batch=AsyncMock(return_value=responses),
    )

    with (
        patch("services.critique_council.get_provider", return_value=fake_provider),
        patch("services.critique_council.isinstance", return_value=True),
        patch("services.critique_council._persist_apiusage", AsyncMock()),
    ):
        report = await critique_bundle(
            resume_text="r",
            cover_letter_text="c",
            job_desc="j",
            session=session,
            user_id=1,
            settings=settings,
        )

    assert report.should_regenerate is False
    assert report.majority_recommendation == "ship"
    assert report.consensus_concerns == []


@pytest.mark.asyncio
async def test_critique_all_personas_fail_returns_degraded():
    """When every persona errors, degraded_reason is set + no regen."""
    from llm.anthropic import BatchResponse

    settings = _settings()
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda r: None

    responses = [
        BatchResponse(custom_id=p, succeeded=False, error="x")
        for p in ("faang_l5_l6_hm", "startup_founder", "fortune_500_hr")
    ]

    fake_provider = SimpleNamespace(
        provider_id="anthropic",
        model_name="claude-3.5-sonnet-20250219",
        estimate_cost=lambda *, input_tokens, output_tokens: 0.0,
        batch=AsyncMock(return_value=responses),
    )

    with (
        patch("services.critique_council.get_provider", return_value=fake_provider),
        patch("services.critique_council.isinstance", return_value=True),
        patch("services.critique_council._persist_apiusage", AsyncMock()),
    ):
        report = await critique_bundle(
            resume_text="r",
            cover_letter_text="c",
            job_desc="j",
            session=session,
            user_id=1,
            settings=settings,
        )

    assert report.degraded_reason == "all_personas_failed"
    assert report.should_regenerate is False


def test_similarity_threshold_constant_matches_plan():
    """T4 specifies difflib similarity >= 0.6 for consensus matching."""
    assert CONSENSUS_SIMILARITY_THRESHOLD == 0.6


def test_critique_personas_prompt_builders():
    """Each persona prompt builder produces non-empty formatted text."""
    from llm.prompts.critique_personas import PROMPT_BUILDERS

    for _persona, builder in PROMPT_BUILDERS.items():
        out = builder("resume here", "cover here", "job desc here")
        assert "resume here" in out
        assert "cover here" in out
        assert "job desc here" in out
        assert len(out) > 100
