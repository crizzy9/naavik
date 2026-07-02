"""Layered scoring orchestrator — plan 65 § D.6.

Covers layer routing (visa zero-out, below tag floor, below LLM gate,
cost-cap exhausted, LLM-failed, happy path), persistence schema (T7
match_breakdown shape), suggested_bullets ID validation (T9), and
`score_unscored_jobs` cron entry behavior.
"""

from __future__ import annotations

import os  # noqa: I001

os.environ.setdefault("NAAVIK_DEBUG", "1")

from datetime import UTC, datetime  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import pytest  # noqa: E402

from llm.prompts.score_job import JobScore  # noqa: E402
from models import VisaSponsorship  # noqa: E402
from services.scorer import orchestrator  # noqa: E402

pytestmark = pytest.mark.uses_sample_data_shims


def _profile_stub(*, needs_sponsorship: bool = False, id_: int = 100, user_id: int = 1):
    return SimpleNamespace(
        id=id_,
        user_id=user_id,
        full_name="Shyam Padia",
        headline="Senior SWE",
        summary_short="Builder",
        summary_full=None,
        visa_sponsorship_needed=(
            VisaSponsorship.NEEDED_NOW if needs_sponsorship else VisaSponsorship.NOT_NEEDED
        ),
        updated_at=datetime.now(UTC),
    )


def _job_stub(
    *,
    id_: int = 7,
    tags: list[str] | None = None,
    visa_restrictions: str | None = None,
    user_id: int = 1,
):
    job = SimpleNamespace(
        id=id_,
        user_id=user_id,
        company="Acme",
        role="Staff SWE",
        description="Build cool things with AI.",
        tags=tags if tags is not None else ["ai-ml", "platform"],
        skills_required=["python"],
        visa_restrictions=visa_restrictions,
        score=0.0,
        score_explanation=None,
        match_breakdown={},
        updated_at=datetime.now(UTC),
        deleted_at=None,
    )
    return job


def _settings_stub(*, cap: float | None = None):
    return SimpleNamespace(
        daily_llm_cost_cap_usd=cap,
        llm_provider="anthropic",
        llm_model="claude-sonnet-4-6",
        score_per_dim_weights={},
    )


def _mock_session(exec_returns: list):
    """Return a MagicMock session whose .exec returns the provided list."""
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()

    async def _exec(*args, **kwargs):
        if exec_returns:
            return exec_returns.pop(0)
        return MagicMock(all=lambda: [], one_or_none=lambda: None)

    session.exec = AsyncMock(side_effect=_exec)
    return session


# ── Layer 1a — visa zero-out ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_orchestrator_visa_zero_out_short_circuits():
    profile = _profile_stub(needs_sponsorship=True)
    job = _job_stub(visa_restrictions="us_citizen_only")
    settings = _settings_stub()

    session = _mock_session([])

    out = await orchestrator.score_job_layered(
        session,
        user_id=1,
        job=job,
        profile=profile,
        settings=settings,
    )
    assert out.score == 0.0
    assert out.visa_concern is True
    assert job.score == 0.0
    assert job.match_breakdown["layers_run"] == ["visa"]
    assert job.match_breakdown["judge_skipped"] is True
    assert job.match_breakdown["judge_skipped_reason"] == "visa_zeroed"
    assert job.match_breakdown["schema_version"] == 1


# ── Layer 1b — below tag floor ───────────────────────────────────────


@pytest.mark.asyncio
async def test_orchestrator_below_tag_floor_short_circuits():
    """Empty profile tags → tag_score = 0 → below floor 0.10."""
    profile = _profile_stub()
    job = _job_stub(tags=["ai-ml"])
    settings = _settings_stub()

    # aggregated_profile_tags returns frozenset() (no bullets) → tag_score=0
    session = _mock_session([MagicMock(all=lambda: [])])

    out = await orchestrator.score_job_layered(
        session,
        user_id=1,
        job=job,
        profile=profile,
        settings=settings,
    )
    assert out.score == 0.0
    assert job.match_breakdown["layers_run"] == ["tag"]
    assert job.match_breakdown["judge_skipped_reason"] == "below_tag_floor"
    assert job.match_breakdown["tag_score"] == 0.0


# ── Layer 2 — below LLM gate (semantic skipped) ──────────────────────


@pytest.mark.asyncio
async def test_orchestrator_below_llm_gate_skips_judge():
    """Tag-only path: profile tags partially cover job's tags; below 0.50."""
    profile = _profile_stub()
    # Job has 5 tags, profile has 1 matched → tag_score = 1/5 = 0.20
    job = _job_stub(tags=["ai-ml", "frontend", "devops", "leadership", "platform"])
    settings = _settings_stub()

    # aggregated_profile_tags → {"ai-ml"}; semantic → None (no embedding).
    session = _mock_session(
        [
            MagicMock(all=lambda: [["ai-ml"]]),  # bullets/tags
            MagicMock(one_or_none=lambda: None),  # ProfileEmbedding
        ]
    )

    out = await orchestrator.score_job_layered(
        session,
        user_id=1,
        job=job,
        profile=profile,
        settings=settings,
    )
    assert out.score == pytest.approx(0.20, abs=0.01)
    assert job.match_breakdown["layers_run"] == ["tag"]
    assert job.match_breakdown["judge_skipped_reason"] == "below_llm_gate"


# ── Layer 3 — cost cap exhausted ─────────────────────────────────────


@pytest.mark.asyncio
async def test_orchestrator_cost_cap_falls_back_to_composite():
    profile = _profile_stub()
    # tag_score = 4/4 = 1.0 → composite = 0.4*1 + 0 = 0.4 (no semantic, below gate)
    # To trigger cost-cap fallback we need composite >= LLM_GATE (0.50).
    # tag_score=1.0 + semantic=1.0 → composite = 0.4 + 0.6 = 1.0 — clears gate.
    job = _job_stub(tags=["ai-ml", "platform"])
    settings = _settings_stub(cap=0.001)  # cap will be exhausted

    profile_emb = SimpleNamespace(embedding=[0.1] * 768, user_id=1)
    session = _mock_session(
        [
            MagicMock(all=lambda: [["ai-ml", "platform"]]),  # bullets/tags
            MagicMock(one_or_none=lambda: profile_emb),  # profile_embedding
        ]
    )

    # Force semantic_score → 1.0 + cost-cap → True
    with (
        patch.object(orchestrator, "_semantic_score", new=AsyncMock(return_value=1.0)),
        patch.object(orchestrator, "cost_cap_exhausted", new=AsyncMock(return_value=True)),
    ):
        out = await orchestrator.score_job_layered(
            session,
            user_id=1,
            job=job,
            profile=profile,
            settings=settings,
        )
    assert out.score == pytest.approx(1.0, abs=0.01)
    assert job.match_breakdown["judge_skipped_reason"] == "cost_cap_exhausted"
    assert job.match_breakdown["layers_run"] == ["tag", "semantic"]


# ── Layer 4 — LLM failed (graceful) ──────────────────────────────────


@pytest.mark.asyncio
async def test_orchestrator_llm_failed_falls_back_to_composite():
    profile = _profile_stub()
    job = _job_stub(tags=["ai-ml", "platform"])
    settings = _settings_stub()

    profile_emb = SimpleNamespace(embedding=[0.1] * 768, user_id=1)
    session = _mock_session(
        [
            MagicMock(all=lambda: [["ai-ml", "platform"]]),  # bullets/tags
            MagicMock(one_or_none=lambda: profile_emb),  # ProfileEmbedding
            MagicMock(all=lambda: []),  # candidate bullets
        ]
    )

    with (
        patch.object(orchestrator, "_semantic_score", new=AsyncMock(return_value=1.0)),
        patch.object(orchestrator, "cost_cap_exhausted", new=AsyncMock(return_value=False)),
        patch.object(
            orchestrator,
            "_llm_judge_score",
            new=AsyncMock(return_value=(None, "llm_failed")),
        ),
    ):
        out = await orchestrator.score_job_layered(
            session,
            user_id=1,
            job=job,
            profile=profile,
            settings=settings,
        )
    assert out.score == pytest.approx(1.0, abs=0.01)
    assert job.match_breakdown["judge_skipped"] is True
    assert job.match_breakdown["judge_skipped_reason"] == "llm_failed"


# ── Layer 4 — Happy path ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_orchestrator_happy_path_persists_llm_score():
    profile = _profile_stub()
    job = _job_stub(tags=["ai-ml", "platform"])
    settings = _settings_stub()

    profile_emb = SimpleNamespace(embedding=[0.1] * 768, user_id=1)
    judge = JobScore(
        score=0.86,
        explanation="Strong fit",
        matched_tags=["ai-ml", "platform"],
        per_dimension={"ai-ml": 0.95, "platform": 0.85},
        strengths=["Built ML platforms"],
        gaps=["k8s"],
        suggested_bullets=[],
    )

    session = _mock_session(
        [
            MagicMock(all=lambda: [["ai-ml", "platform"]]),  # bullets/tags
            MagicMock(one_or_none=lambda: profile_emb),  # ProfileEmbedding
            MagicMock(all=lambda: []),  # candidate bullets
        ]
    )

    with (
        patch.object(orchestrator, "_semantic_score", new=AsyncMock(return_value=0.9)),
        patch.object(orchestrator, "cost_cap_exhausted", new=AsyncMock(return_value=False)),
        patch.object(
            orchestrator,
            "_llm_judge_score",
            new=AsyncMock(return_value=(judge, None)),
        ),
    ):
        out = await orchestrator.score_job_layered(
            session,
            user_id=1,
            job=job,
            profile=profile,
            settings=settings,
        )
    assert out.score == 0.86
    assert job.match_breakdown["layers_run"] == ["tag", "semantic", "llm_judge"]
    assert job.match_breakdown["judge_skipped"] is False
    assert job.match_breakdown["layer_4_provider"] == "anthropic"
    assert job.match_breakdown["per_dimension"]["ai-ml"] == 0.95


# ── Persistence schema (T7) ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_match_breakdown_has_all_canonical_keys():
    profile = _profile_stub()
    job = _job_stub(tags=["ai-ml", "platform"])
    settings = _settings_stub()
    profile_emb = SimpleNamespace(embedding=[0.1] * 768, user_id=1)

    judge = JobScore(score=0.86, explanation="Fit")
    session = _mock_session(
        [
            MagicMock(all=lambda: [["ai-ml", "platform"]]),
            MagicMock(one_or_none=lambda: profile_emb),
            MagicMock(all=lambda: []),
        ]
    )

    with (
        patch.object(orchestrator, "_semantic_score", new=AsyncMock(return_value=0.9)),
        patch.object(orchestrator, "cost_cap_exhausted", new=AsyncMock(return_value=False)),
        patch.object(
            orchestrator,
            "_llm_judge_score",
            new=AsyncMock(return_value=(judge, None)),
        ),
    ):
        await orchestrator.score_job_layered(
            session,
            user_id=1,
            job=job,
            profile=profile,
            settings=settings,
        )

    required_keys = {
        "score",
        "per_dimension",
        "matched_tags",
        "strengths",
        "gaps",
        "suggested_bullets",
        "visa_concern",
        "visa_note",
        "layers_run",
        "judge_skipped",
        "judge_skipped_reason",
        "layer_4_provider",
        "layer_4_model",
        "scored_at",
        "tag_score",
        "semantic_score",
        "composite_pre_llm",
        "schema_version",
    }
    assert required_keys.issubset(job.match_breakdown.keys())


# ── Score-write semantics (T8) ───────────────────────────────────────


@pytest.mark.asyncio
async def test_score_updates_bump_updated_at():
    profile = _profile_stub(needs_sponsorship=True)
    job = _job_stub(visa_restrictions="us_citizen_only")
    settings = _settings_stub()
    pre_updated = job.updated_at

    session = _mock_session([])

    # tiny pause so monotonic clocks definitely differ
    import asyncio

    await asyncio.sleep(0.001)

    await orchestrator.score_job_layered(
        session,
        user_id=1,
        job=job,
        profile=profile,
        settings=settings,
    )
    assert job.updated_at > pre_updated


# ── suggested_bullets validation (T9) ────────────────────────────────


@pytest.mark.asyncio
async def test_filter_valid_bullet_ids_drops_hallucinated():
    """The orchestrator filters non-existent bullet IDs from LLM output."""
    session = MagicMock()
    # Query returns only id=1 — the LLM claimed 1, 2, 99.
    session.exec = AsyncMock(return_value=MagicMock(all=lambda: [1]))

    out = await orchestrator._filter_valid_bullet_ids(
        session, user_id=1, profile_id=10, ids=[1, 2, 99]
    )
    # Order preserved from LLM, hallucinated dropped.
    assert out == [1]


@pytest.mark.asyncio
async def test_filter_valid_bullet_ids_empty_input():
    out = await orchestrator._filter_valid_bullet_ids(MagicMock(), user_id=1, profile_id=10, ids=[])
    assert out == []


# ── source_trust_weight forward-compat seam (T9) ─────────────────────


@pytest.mark.asyncio
async def test_source_trust_weight_default_one_no_change():
    """Default 1.0 → no multiplier effect."""
    profile = _profile_stub(needs_sponsorship=True)
    job = _job_stub(visa_restrictions="us_citizen_only")
    settings = _settings_stub()
    session = _mock_session([])

    out = await orchestrator.score_job_layered(
        session,
        user_id=1,
        job=job,
        profile=profile,
        settings=settings,
        source_trust_weight=1.0,
    )
    assert out.score == 0.0  # visa zeroed regardless


@pytest.mark.asyncio
async def test_source_trust_weight_halves_below_floor_composite():
    """Below-floor composite = tag_score * source_trust_weight."""
    profile = _profile_stub()
    job = _job_stub(tags=["ai-ml", "frontend"])  # 1/2 = 0.5 tag — clears floor
    settings = _settings_stub()

    session = _mock_session(
        [
            MagicMock(all=lambda: [["ai-ml"]]),
            MagicMock(one_or_none=lambda: None),
        ]
    )

    out = await orchestrator.score_job_layered(
        session,
        user_id=1,
        job=job,
        profile=profile,
        settings=settings,
        source_trust_weight=0.5,
    )
    # tag_score=0.5, no semantic → composite=0.5, *0.5 = 0.25 below LLM gate
    assert out.score == pytest.approx(0.25, abs=0.01)


# ── Cron entrypoint (T10) ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_score_unscored_jobs_returns_zero_when_no_users():
    session = _mock_session([MagicMock(all=lambda: [])])
    n = await orchestrator.score_unscored_jobs(session)
    assert n == 0


@pytest.mark.asyncio
async def test_score_unscored_jobs_skips_when_no_profile():
    """Settings exists but Profile missing → skip (don't crash)."""
    settings = _settings_stub()
    settings.user_id = 1
    settings.semantic_match_enabled = True
    session = _mock_session(
        [
            MagicMock(all=lambda: [settings]),
            MagicMock(one_or_none=lambda: None),  # profile missing
        ]
    )
    n = await orchestrator.score_unscored_jobs(session)
    assert n == 0


# ── Backward-compat re-exports (T11) ─────────────────────────────────


def test_backward_compat_apply_visa_filter_re_export():
    """The package-split must preserve `from services.scorer import ...` callers."""
    from services.scorer import apply_visa_filter, needs_visa_zero_out

    assert callable(apply_visa_filter)
    assert callable(needs_visa_zero_out)


def test_lazy_orchestrator_re_export():
    """`from services.scorer import score_job_layered` works via __getattr__."""
    from services.scorer import score_job_layered

    assert callable(score_job_layered)


# unused-import placeholders
_ = (UTC, datetime)
