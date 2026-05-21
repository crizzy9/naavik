"""Layer 1b — tag overlap + weight resolution (plan 65 § D.2).

Covers `_tag_overlap_score` formula, `aggregated_profile_tags` (with soft-
deleted filter + multi-experience union), and `resolve_weights` defaults
+ clamping behavior.
"""

from __future__ import annotations

import os  # noqa: I001

os.environ.setdefault("NAAVIK_DEBUG", "1")

from datetime import UTC, datetime  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from unittest.mock import AsyncMock, MagicMock  # noqa: E402

import pytest  # noqa: E402

from services.scorer.tag_layer import _tag_overlap_score, aggregated_profile_tags  # noqa: E402
from services.scorer.weights import PerDimWeights, resolve_weights  # noqa: E402

# ── _tag_overlap_score formula ────────────────────────────────────────


def test_overlap_perfect_match():
    job_tags = ["ai-ml", "backend"]
    profile_tags = frozenset({"ai-ml", "backend"})
    weights = {"ai-ml": 1.0, "backend": 1.0}
    assert _tag_overlap_score(job_tags, profile_tags, weights) == 1.0


def test_overlap_partial_match():
    job_tags = ["ai-ml", "backend", "frontend"]
    profile_tags = frozenset({"ai-ml", "backend"})
    weights = dict.fromkeys(("ai-ml", "backend", "frontend"), 1.0)
    # 2/3 weighted overlap.
    assert _tag_overlap_score(job_tags, profile_tags, weights) == pytest.approx(2 / 3)


def test_overlap_zero_when_disjoint():
    job_tags = ["frontend"]
    profile_tags = frozenset({"ai-ml", "backend"})
    weights = {"frontend": 1.0, "ai-ml": 1.0, "backend": 1.0}
    assert _tag_overlap_score(job_tags, profile_tags, weights) == 0.0


def test_overlap_empty_job_tags_returns_zero():
    assert _tag_overlap_score([], frozenset({"ai-ml"}), {"ai-ml": 1.0}) == 0.0


def test_overlap_empty_profile_tags_returns_zero():
    assert _tag_overlap_score(["ai-ml"], frozenset(), {"ai-ml": 1.0}) == 0.0


def test_overlap_asymmetric_extra_profile_tags_no_penalty():
    """Profile breadth doesn't lower score — that's the asymmetry."""
    job_tags = ["ai-ml"]
    profile_tags = frozenset({"ai-ml", "backend", "frontend", "leadership"})
    weights = dict.fromkeys(("ai-ml", "backend", "frontend", "leadership"), 1.0)
    # Full coverage of the job's 1 tag — score 1.0 even with extra profile breadth.
    assert _tag_overlap_score(job_tags, profile_tags, weights) == 1.0


def test_overlap_custom_weights_bias_score():
    job_tags = ["ai-ml", "frontend"]
    profile_tags = frozenset({"ai-ml"})
    weights = {"ai-ml": 2.0, "frontend": 1.0}
    # numerator = 2.0 (ai-ml in both) | denominator = 3.0 (ai-ml + frontend in job)
    assert _tag_overlap_score(job_tags, profile_tags, weights) == pytest.approx(2 / 3)


def test_overlap_unknown_tag_falls_back_to_unit_weight():
    """Missing weight key defaults to 1.0 inside the helper."""
    job_tags = ["unknown-tag", "ai-ml"]
    profile_tags = frozenset({"ai-ml"})
    weights = {"ai-ml": 1.0}  # no entry for unknown-tag
    # numerator = 1.0 | denominator = 1.0 (ai-ml) + 1.0 (default) = 2.0
    assert _tag_overlap_score(job_tags, profile_tags, weights) == pytest.approx(0.5)


def test_overlap_zero_denominator_guard():
    """When weights are zeroed out for the job tags, score is 0."""
    job_tags = ["ai-ml"]
    profile_tags = frozenset({"ai-ml"})
    weights = {"ai-ml": 0.0}
    assert _tag_overlap_score(job_tags, profile_tags, weights) == 0.0


# ── aggregated_profile_tags ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_aggregated_profile_tags_unions_multi_experience():
    profile = SimpleNamespace(id=1)

    session = MagicMock()
    session.exec = AsyncMock(
        return_value=MagicMock(
            all=lambda: [
                ["ai-ml", "backend"],
                ["leadership", "ai-ml"],
                ["platform"],
            ]
        )
    )

    out = await aggregated_profile_tags(session, profile=profile)
    assert out == frozenset({"ai-ml", "backend", "leadership", "platform"})


@pytest.mark.asyncio
async def test_aggregated_profile_tags_drops_unknown():
    profile = SimpleNamespace(id=1)
    session = MagicMock()
    session.exec = AsyncMock(
        return_value=MagicMock(all=lambda: [["ai-ml", "garbage-tag", "leadership"]])
    )
    out = await aggregated_profile_tags(session, profile=profile)
    assert out == frozenset({"ai-ml", "leadership"})


@pytest.mark.asyncio
async def test_aggregated_profile_tags_empty():
    profile = SimpleNamespace(id=1)
    session = MagicMock()
    session.exec = AsyncMock(return_value=MagicMock(all=lambda: []))
    assert await aggregated_profile_tags(session, profile=profile) == frozenset()


@pytest.mark.asyncio
async def test_aggregated_profile_tags_none_profile():
    session = MagicMock()
    assert await aggregated_profile_tags(session, profile=None) == frozenset()


# ── resolve_weights / PerDimWeights validator ─────────────────────────


def test_resolve_weights_empty_settings_defaults_all_one():
    settings = SimpleNamespace(score_per_dim_weights=None)
    weights = resolve_weights(settings)
    assert all(v == 1.0 for v in weights.values())
    # Every Tag should be present.
    assert "ai-ml" in weights
    assert "leadership" in weights


def test_resolve_weights_partial_keys_fills_default():
    settings = SimpleNamespace(score_per_dim_weights={"ai-ml": 2.0})
    weights = resolve_weights(settings)
    assert weights["ai-ml"] == 2.0
    assert weights["backend"] == 1.0


def test_resolve_weights_clamps_to_range():
    settings = SimpleNamespace(score_per_dim_weights={"ai-ml": 5.0, "backend": -1.0})
    weights = resolve_weights(settings)
    assert weights["ai-ml"] == 3.0
    assert weights["backend"] == 0.0


def test_per_dim_weights_drops_unknown_keys():
    raw = {"ai-ml": 1.5, "garbage-key": 2.0}
    validated = PerDimWeights(root=raw).root
    assert "garbage-key" not in validated
    assert validated["ai-ml"] == 1.5


def test_per_dim_weights_drops_non_numeric():
    raw = {"ai-ml": "not-a-number", "backend": 1.0}
    validated = PerDimWeights(root=raw).root
    assert "ai-ml" not in validated
    assert validated["backend"] == 1.0


# Silence unused-import warnings for the placeholder datetime/UTC.
_ = (UTC, datetime)
