"""3-agent voting council tests — plan 67 (0.3.4) § C.2 / T14.

Covers Borda math + deterministic tie-break, persona prompt dispatch,
batch API path with mock + sync fallback, and degraded-mode when every
persona fails.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from services.council import (
    SelectedBullets,
    _borda_merge,
    vote_on_bullet_selection,
)

pytestmark = pytest.mark.uses_sample_data_shims


def _settings(**overrides):
    base = {
        "user_id": 1,
        "llm_provider": "anthropic",
        "llm_model": "claude-3.5-sonnet-20250219",
        "originality_api_key": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_borda_consensus_picks_unanimous_top():
    """All 3 personas rank [1,2,3] → top-K returns [1,2,3] in order."""
    rankings = {
        "pragmatic_recruiter": [1, 2, 3],
        "hiring_manager": [1, 2, 3],
        "cultural_fit": [1, 2, 3],
    }
    selected, scores = _borda_merge(rankings, {1, 2, 3}, top_k=3)
    assert selected == [1, 2, 3]
    # 3 personas × (3 - rank); 1 = 3+3+3 = 9, 2 = 2+2+2 = 6, 3 = 1+1+1 = 3.
    assert scores == {1: 9, 2: 6, 3: 3}


def test_borda_tie_break_by_lower_bullet_id():
    """When two bullets tie on Borda score, the lower bullet_id wins."""
    # Forced tie: persona A ranks [1, 2]; persona B ranks [2, 1].
    # Scores: 1 = 2+1 = 3; 2 = 1+2 = 3. Lower id (1) wins.
    rankings_real_tie = {
        "pragmatic_recruiter": [1, 2],
        "hiring_manager": [2, 1],
        "cultural_fit": [],
    }
    selected_tie, _ = _borda_merge(rankings_real_tie, {1, 2}, top_k=2)
    assert selected_tie == [1, 2]


def test_borda_drops_unknown_ids():
    """IDs in persona ranking not in candidate set are silently dropped."""
    rankings = {
        "pragmatic_recruiter": [99, 1, 2],  # 99 not in candidate set
        "hiring_manager": [1, 2],
        "cultural_fit": [2, 1],
    }
    selected, scores = _borda_merge(rankings, {1, 2}, top_k=2)
    assert set(selected) == {1, 2}
    assert 99 not in scores


def test_borda_disagreement_picks_highest_aggregate():
    """Heavy disagreement still produces deterministic top-K."""
    rankings = {
        "pragmatic_recruiter": [1, 2, 3, 4],
        "hiring_manager": [4, 3, 2, 1],
        "cultural_fit": [2, 4, 1, 3],
    }
    # Scores: 1 = 4+1+2 = 7; 2 = 3+2+4 = 9; 3 = 2+3+1 = 6; 4 = 1+4+3 = 8.
    selected, scores = _borda_merge(rankings, {1, 2, 3, 4}, top_k=2)
    assert selected == [2, 4]  # top 2 by Borda


def test_borda_ignores_duplicates_within_persona():
    """If a persona repeats an id (model misbehavior), only the first counts."""
    rankings = {
        "pragmatic_recruiter": [1, 1, 2],
        "hiring_manager": [2, 1],
        "cultural_fit": [],
    }
    # Persona 1: rank 0 = 1 gets 3 (n=3); rank 1 = 1 (dup) skipped; rank 2 = 2 gets 1.
    # Persona 2: rank 0 = 2 gets 3; rank 1 = 1 gets 2.
    # Scores: 1 = 3+2 = 5; 2 = 1+3 = 4.
    selected, scores = _borda_merge(rankings, {1, 2}, top_k=2)
    assert selected == [1, 2]


def test_borda_empty_candidates_returns_empty():
    selected, scores = _borda_merge({}, set(), top_k=8)
    assert selected == []
    assert scores == {}


@pytest.mark.asyncio
async def test_vote_empty_candidates_short_circuits():
    """Empty candidate list returns empty SelectedBullets without LLM call."""
    session = AsyncMock()
    settings = _settings()
    with patch("services.council.get_provider") as gp:
        result = await vote_on_bullet_selection(
            [],
            {"role": "Eng", "description": "build", "skills_required": [], "company": "X"},
            session=session,
            user_id=1,
            settings=settings,
        )
    assert isinstance(result, SelectedBullets)
    assert result.selected_ids == []
    assert result.batch_used is False
    gp.assert_not_called()


@pytest.mark.asyncio
async def test_vote_via_batch_api_happy_path():
    """Anthropic batch API path → 3 personas → Borda merge → selected_ids."""
    from llm.anthropic import BatchResponse

    settings = _settings()
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda r: None

    candidate_bullets = [{"id": i, "text": f"bullet {i}"} for i in (1, 2, 3, 4, 5)]
    job = {
        "role": "Eng",
        "description": "build payments",
        "skills_required": ["python"],
        "company": "Stripe",
    }

    batch_responses = [
        BatchResponse(
            custom_id="pragmatic_recruiter",
            value={"ranked_bullet_ids": [1, 2, 3, 4, 5], "rationale": "ATS"},
            input_tokens=100,
            output_tokens=50,
            succeeded=True,
        ),
        BatchResponse(
            custom_id="hiring_manager",
            value={"ranked_bullet_ids": [2, 1, 3, 5, 4], "rationale": "depth"},
            input_tokens=100,
            output_tokens=50,
            succeeded=True,
        ),
        BatchResponse(
            custom_id="cultural_fit",
            value={"ranked_bullet_ids": [1, 3, 2, 4, 5], "rationale": "growth"},
            input_tokens=100,
            output_tokens=50,
            succeeded=True,
        ),
    ]

    fake_provider = SimpleNamespace(
        provider_id="anthropic",
        model_name="claude-3.5-sonnet-20250219",
        estimate_cost=lambda *, input_tokens, output_tokens: 0.001,
        batch=AsyncMock(return_value=batch_responses),
    )

    with (
        patch("services.council.get_provider", return_value=fake_provider),
        patch("services.council.isinstance", return_value=True),
        patch("services.council._persist_apiusage", AsyncMock()),
    ):
        result = await vote_on_bullet_selection(
            candidate_bullets,
            job,
            session=session,
            user_id=1,
            settings=settings,
            top_k=3,
        )

    assert result.batch_used is True
    assert len(result.selected_ids) == 3
    assert result.degraded_reason is None
    assert set(result.persona_rankings.keys()) == {
        "pragmatic_recruiter",
        "hiring_manager",
        "cultural_fit",
    }


@pytest.mark.asyncio
async def test_vote_batch_failure_falls_back_to_sync():
    """When batch API raises LLMProviderError, sync gather completes the work."""
    from llm.base import LLMProviderError

    settings = _settings()
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda r: None

    candidate_bullets = [{"id": i, "text": f"b{i}"} for i in (1, 2, 3)]
    job = {"role": "Eng", "description": "x", "skills_required": [], "company": "C"}

    fake_provider = SimpleNamespace(
        provider_id="anthropic",
        model_name="claude-3.5-sonnet-20250219",
        estimate_cost=lambda *, input_tokens, output_tokens: 0.001,
        batch=AsyncMock(side_effect=LLMProviderError("batch 503")),
    )

    sync_returns = [
        SimpleNamespace(
            value={"ranked_bullet_ids": [1, 2, 3]},
            text="",
            input_tokens=10,
            output_tokens=5,
        ),
        SimpleNamespace(
            value={"ranked_bullet_ids": [2, 1, 3]},
            text="",
            input_tokens=10,
            output_tokens=5,
        ),
        SimpleNamespace(
            value={"ranked_bullet_ids": [3, 2, 1]},
            text="",
            input_tokens=10,
            output_tokens=5,
        ),
    ]
    sync_call = AsyncMock(side_effect=sync_returns)

    with (
        patch("services.council.get_provider", return_value=fake_provider),
        patch("services.council.isinstance", return_value=True),
        patch("services.council.llm_tracker.tracked_call", sync_call),
    ):
        result = await vote_on_bullet_selection(
            candidate_bullets,
            job,
            session=session,
            user_id=1,
            settings=settings,
            top_k=3,
        )

    assert result.batch_used is False
    assert sync_call.await_count == 3
    assert len(result.selected_ids) == 3


@pytest.mark.asyncio
async def test_vote_all_personas_fail_returns_degraded():
    """When every persona errors, return empty selection with degraded_reason."""
    from llm.anthropic import BatchResponse

    settings = _settings()
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda r: None

    candidate_bullets = [{"id": 1, "text": "x"}]
    job = {"role": "E", "description": "", "skills_required": [], "company": ""}

    failed_responses = [
        BatchResponse(custom_id=p, succeeded=False, error="oops")
        for p in ("pragmatic_recruiter", "hiring_manager", "cultural_fit")
    ]

    fake_provider = SimpleNamespace(
        provider_id="anthropic",
        model_name="claude-3.5-sonnet-20250219",
        estimate_cost=lambda *, input_tokens, output_tokens: 0.0,
        batch=AsyncMock(return_value=failed_responses),
    )

    with (
        patch("services.council.get_provider", return_value=fake_provider),
        patch("services.council.isinstance", return_value=True),
        patch("services.council._persist_apiusage", AsyncMock()),
    ):
        result = await vote_on_bullet_selection(
            candidate_bullets,
            job,
            session=session,
            user_id=1,
            settings=settings,
            top_k=3,
        )

    assert result.degraded_reason == "all_personas_failed"
    assert result.selected_ids == []


def test_persona_prompt_builders_format_correctly():
    """Each persona builder produces a non-empty string with bullet ids."""
    from llm.prompts.council_personas import PROMPT_BUILDERS

    candidates = [{"id": 7, "text": "led a thing"}]
    job = {"role": "SWE", "description": "build", "skills_required": ["py"], "company": "X"}
    for _persona, builder in PROMPT_BUILDERS.items():
        out = builder(candidates, job)
        assert "7" in out
        assert "led a thing" in out
        assert len(out) > 100
