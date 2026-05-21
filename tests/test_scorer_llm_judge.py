"""Layer 4 — LLM-as-judge (plan 65 § D.5).

Covers `cost_cap_exhausted` probe (T1), `_llm_judge_score` graceful
degrade paths (no provider → "no_provider", LLM error → "llm_failed"),
plus `JobScore` validator behavior (drops unknown per_dim keys, truncates
bullet strings, clamps per_dim values to [0, 1]).
"""

from __future__ import annotations

import os  # noqa: I001

os.environ.setdefault("NAAVIK_DEBUG", "1")

from datetime import UTC, datetime  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import pytest  # noqa: E402

from llm import LLMProviderError  # noqa: E402
from llm.base import StructuredResult  # noqa: E402
from llm.prompts.score_job import JobScore  # noqa: E402
from services.scorer import (
    _ESTIMATED_JUDGE_COST_USD,  # noqa: E402
    llm_judge,  # noqa: E402
)


def _settings_stub(cap: float | None = None):
    return SimpleNamespace(
        daily_llm_cost_cap_usd=cap,
        llm_provider="anthropic",
        llm_model="claude-3.5-sonnet-20250219",
    )


def _profile_stub():
    return SimpleNamespace(
        full_name="Shyam Padia",
        headline="Senior SWE @ Intuit",
        summary_short="Builder",
        summary_full=None,
    )


def _job_stub():
    return SimpleNamespace(
        id=10,
        user_id=1,
        company="Acme",
        role="Staff SWE",
        description="Build cool things with AI.",
        tags=["ai-ml", "platform"],
        skills_required=["python"],
        visa_restrictions=None,
    )


def _bullet_stub(id_: int, text: str):
    return SimpleNamespace(id=id_, text=text, tags=["ai-ml"])


# ── cost_cap_exhausted (T1) ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_cost_cap_unset_returns_false():
    session = AsyncMock()
    settings = _settings_stub(cap=None)
    assert not await llm_judge.cost_cap_exhausted(session, user_id=1, settings=settings)


@pytest.mark.asyncio
async def test_cost_cap_well_under_returns_false():
    session = AsyncMock()
    settings = _settings_stub(cap=10.0)
    with patch.object(llm_judge.llm_tracker, "today_cost_usd", new=AsyncMock(return_value=0.5)):
        assert not await llm_judge.cost_cap_exhausted(session, user_id=1, settings=settings)


@pytest.mark.asyncio
async def test_cost_cap_at_boundary_returns_true():
    """today_spend + estimated > cap → True."""
    session = AsyncMock()
    settings = _settings_stub(cap=1.0)
    with patch.object(
        llm_judge.llm_tracker,
        "today_cost_usd",
        new=AsyncMock(return_value=1.0 - _ESTIMATED_JUDGE_COST_USD / 2),
    ):
        assert await llm_judge.cost_cap_exhausted(session, user_id=1, settings=settings)


@pytest.mark.asyncio
async def test_cost_cap_over_returns_true():
    session = AsyncMock()
    settings = _settings_stub(cap=1.0)
    with patch.object(llm_judge.llm_tracker, "today_cost_usd", new=AsyncMock(return_value=2.0)):
        assert await llm_judge.cost_cap_exhausted(session, user_id=1, settings=settings)


# ── _llm_judge_score graceful-degrade paths ──────────────────────────


@pytest.mark.asyncio
async def test_llm_judge_no_provider_returns_no_provider_skip():
    """get_provider raises LLMProviderError → ("no_provider")."""
    session = AsyncMock()
    settings = _settings_stub()

    def _raise(_):
        raise LLMProviderError("no llm_provider configured", kind="auth_required")

    with patch.object(llm_judge, "get_provider", side_effect=_raise):
        score, reason = await llm_judge._llm_judge_score(
            session,
            user_id=1,
            job=_job_stub(),
            profile=_profile_stub(),
            candidate_bullets=[],
            tag_score=0.7,
            semantic_score=0.6,
            settings=settings,
        )
    assert score is None
    assert reason == "no_provider"


@pytest.mark.asyncio
async def test_llm_judge_provider_error_returns_llm_failed():
    session = AsyncMock()
    settings = _settings_stub()

    class _FakeProvider:
        provider_id = "anthropic"
        model_name = "claude-3.5-sonnet-20250219"

    async def _raising(**kwargs):
        raise LLMProviderError("boom", kind="provider_error")

    with (
        patch.object(llm_judge, "get_provider", return_value=_FakeProvider()),
        patch.object(llm_judge.llm_tracker, "tracked_call", side_effect=_raising),
    ):
        score, reason = await llm_judge._llm_judge_score(
            session,
            user_id=1,
            job=_job_stub(),
            profile=_profile_stub(),
            candidate_bullets=[],
            tag_score=0.7,
            semantic_score=0.6,
            settings=settings,
        )
    assert score is None
    assert reason == "llm_failed"


@pytest.mark.asyncio
async def test_llm_judge_happy_path_returns_score():
    session = AsyncMock()
    settings = _settings_stub()

    class _FakeProvider:
        provider_id = "anthropic"
        model_name = "claude-3.5-sonnet-20250219"

    js = JobScore(
        score=0.86,
        explanation="Strong fit",
        matched_tags=["ai-ml", "platform"],
        per_dimension={"ai-ml": 0.95, "platform": 0.85},
        strengths=["Built ML platforms"],
        gaps=["k8s"],
        suggested_bullets=[1, 2],
    )

    async def _stub_tracked_call(**kwargs):
        return StructuredResult(
            text="{}",
            value=js.model_dump(),
            input_tokens=100,
            output_tokens=50,
            model="claude-3.5-sonnet-20250219",
        )

    with (
        patch.object(llm_judge, "get_provider", return_value=_FakeProvider()),
        patch.object(llm_judge.llm_tracker, "tracked_call", side_effect=_stub_tracked_call),
    ):
        score, reason = await llm_judge._llm_judge_score(
            session,
            user_id=1,
            job=_job_stub(),
            profile=_profile_stub(),
            candidate_bullets=[_bullet_stub(1, "Did a thing")],
            tag_score=0.7,
            semantic_score=0.85,
            settings=settings,
        )
    assert reason is None
    assert score is not None
    assert score.score == 0.86
    assert "ai-ml" in score.matched_tags


@pytest.mark.asyncio
async def test_llm_judge_validation_failure_returns_llm_failed():
    """When tracked_call returns malformed payload, validation fails →
    skip reason `llm_failed`.
    """
    session = AsyncMock()
    settings = _settings_stub()

    class _FakeProvider:
        provider_id = "anthropic"
        model_name = "claude-3.5-sonnet-20250219"

    async def _stub_tracked_call(**kwargs):
        return StructuredResult(
            text="{}",
            value={"score": 99.0, "explanation": "nope"},  # score > 1 fails validation
            input_tokens=10,
            output_tokens=5,
            model="claude-3.5-sonnet-20250219",
        )

    with (
        patch.object(llm_judge, "get_provider", return_value=_FakeProvider()),
        patch.object(llm_judge.llm_tracker, "tracked_call", side_effect=_stub_tracked_call),
    ):
        score, reason = await llm_judge._llm_judge_score(
            session,
            user_id=1,
            job=_job_stub(),
            profile=_profile_stub(),
            candidate_bullets=[],
            tag_score=0.7,
            semantic_score=0.85,
            settings=settings,
        )
    assert score is None
    assert reason == "llm_failed"


# ── prompt rendering helpers ─────────────────────────────────────────


def test_render_bullets_with_ids_truncates_long_text():
    b = _bullet_stub(1, "x" * 300)
    rendered = llm_judge._render_bullets_with_ids([b])
    assert "[1]" in rendered
    # 200-char cap on the bullet text portion.
    assert len(rendered.split(" ", 1)[1]) <= 210


def test_render_profile_tags_unions_across_bullets():
    bs = [
        SimpleNamespace(id=1, text="a", tags=["ai-ml", "backend"]),
        SimpleNamespace(id=2, text="b", tags=["platform", "ai-ml"]),
    ]
    out = llm_judge._render_profile_tags(SimpleNamespace(), bs)
    assert "ai-ml" in out
    assert "backend" in out
    assert "platform" in out


# ── JobScore validator behavior (T6) ─────────────────────────────────


def test_jobscore_drops_unknown_per_dim_keys():
    js = JobScore(score=0.5, per_dimension={"ai-ml": 0.5, "garbage": 1.0})
    assert "garbage" not in js.per_dimension
    assert js.per_dimension["ai-ml"] == 0.5


def test_jobscore_clamps_per_dim_values():
    js = JobScore(score=0.5, per_dimension={"ai-ml": 5.0, "backend": -2.0})
    assert js.per_dimension["ai-ml"] == 1.0
    assert js.per_dimension["backend"] == 0.0


def test_jobscore_truncates_long_bullet_strings():
    long = "x" * 500
    js = JobScore(score=0.5, gaps=[long])
    assert len(js.gaps[0]) == 120


def test_jobscore_max_gaps_enforced():
    """Pydantic max_length on gaps rejects > 5 entries."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        JobScore(score=0.5, gaps=["a", "b", "c", "d", "e", "f"])


# unused-import placeholders
_ = (UTC, datetime, MagicMock)
