"""Unit tests for `components/score_card.html` (plan 72 / 0.3.2.01).

Covers the Variant B (Linear bento, 3-zone) composite: score circle on the
left, per-dim bars in the middle, strengths/gaps/visa panels on the right,
optional provenance footer when `expanded=True`. Verifies defensive `.get()`
handling so legacy `match_breakdown` rows without the new strength/gap keys
still render (graceful degrade).
"""

from __future__ import annotations

import pytest
from jinja2 import ChainableUndefined, Environment, FileSystemLoader

from ui.templates_setup import STATUS_DOT_COLORS, TAG_VOCAB

_TEMPLATES_DIR = "src/ui/templates"


@pytest.fixture(scope="module")
def env() -> Environment:
    e = Environment(
        loader=FileSystemLoader(_TEMPLATES_DIR),
        autoescape=True,
        undefined=ChainableUndefined,
    )
    e.globals["STATUS_DOT_COLORS"] = STATUS_DOT_COLORS
    e.globals["TAG_VOCAB"] = TAG_VOCAB
    return e


def _full_breakdown() -> dict:
    """18-key shape per `DATA_MODEL.md § Job.match_breakdown`."""
    return {
        "per_dimension": {"ai-ml": 0.95, "platform": 0.88, "leadership": 0.82},
        "strengths": ["Strong ML platform background", "Personalization signal"],
        "gaps": ["No explicit foundation-model experience"],
        "visa_concern": False,
        "visa_note": None,
        "layers_run": ["layer-1", "layer-2", "layer-3"],
        "layer_4_provider": "anthropic",
        "layer_4_model": "claude-opus-4-7",
        "judge_skipped": False,
        "scored_at": "2026-05-20T03:30:00Z",
        "tag_score": 0.91,
        "semantic_score": 0.84,
        "composite_pre_llm": 0.88,
    }


def test_renders_full_18_key_shape(env: Environment) -> None:
    """Full 18-key match_breakdown drives every zone."""
    out = env.get_template("components/score_card.html").render(
        score=86,
        match_breakdown=_full_breakdown(),
        expanded=False,
    )
    # LEFT zone — MATCH label + score circle (86 emerald)
    assert "MATCH" in out
    assert ">86</span>" in out
    assert "stroke-emerald-400" in out  # threshold ≥ 80
    # MIDDLE zone — per-dim bars
    assert "PER-DIMENSION" in out
    assert "ai-ml" in out
    assert "platform" in out
    # RIGHT zone — strengths + gaps tinted panels
    assert "STRENGTHS" in out
    assert "Strong ML platform background" in out
    assert "WHAT&#39;S MISSING" in out or "WHAT'S MISSING" in out
    assert "No explicit foundation-model experience" in out
    # llm-judged pulse dot
    assert "llm-judged" in out


def test_expanded_shows_provenance_footer(env: Environment) -> None:
    """`expanded=True` renders the layer-provenance + scored_at footer."""
    out = env.get_template("components/score_card.html").render(
        score=86,
        match_breakdown=_full_breakdown(),
        expanded=True,
    )
    assert "PROVENANCE" in out
    assert "layer-1" in out
    assert "layer-2" in out
    assert "layer-3" in out
    assert "anthropic" in out
    assert "claude-opus-4-7" in out
    assert "2026-05-20T03:30:00Z" in out


def test_collapsed_omits_provenance_footer(env: Environment) -> None:
    """Default `expanded=False` hides the provenance footer."""
    out = env.get_template("components/score_card.html").render(
        score=86,
        match_breakdown=_full_breakdown(),
    )
    assert "PROVENANCE" not in out
    # Layer chips don't appear in collapsed mode
    assert "2026-05-20T03:30:00Z" not in out


def test_empty_strengths_and_gaps_show_placeholder(env: Environment) -> None:
    """Empty lists render placeholder copy, not blank panels."""
    out = env.get_template("components/score_card.html").render(
        score=72,
        match_breakdown={"per_dimension": {"ai-ml": 0.7}, "strengths": [], "gaps": []},
    )
    assert "STRENGTHS" in out
    assert "no strengths surfaced" in out
    assert "no gaps identified" in out


def test_legacy_breakdown_missing_new_keys_renders_safely(env: Environment) -> None:
    """A pre-plan-65 `match_breakdown` (no `per_dimension` / `strengths` / `gaps`)
    must NOT raise — defensive `.get()` lets the card degrade gracefully.
    """
    legacy = {"ai-ml": 0.95, "platform": 0.88}  # old flat shape, no nested keys
    out = env.get_template("components/score_card.html").render(
        score=86,
        match_breakdown=legacy,
    )
    assert out  # render succeeded
    assert "no per-dimension data" in out
    assert "no strengths surfaced" in out
    assert "no gaps identified" in out


def test_visa_concern_renders_rose_panel(env: Environment) -> None:
    """`visa_concern=True` + `visa_note` set surfaces the rose-tinted visa panel."""
    bd = _full_breakdown()
    bd["visa_concern"] = True
    bd["visa_note"] = "Posting requires US citizenship — sponsorship not available."
    out = env.get_template("components/score_card.html").render(
        score=42,
        match_breakdown=bd,
    )
    assert "VISA" in out
    assert "sponsorship not available" in out
    assert "ring-rose-500/20" in out


def test_visa_concern_without_note_does_not_render_visa_panel(env: Environment) -> None:
    """Concern flag without a note → no panel (graceful)."""
    bd = _full_breakdown()
    bd["visa_concern"] = True
    bd["visa_note"] = None
    out = env.get_template("components/score_card.html").render(
        score=42,
        match_breakdown=bd,
    )
    # Only the right-side rose panel header `VISA` would appear with a note;
    # without the note, the panel doesn't render.
    assert "ring-rose-500/20" not in out


def test_judge_skipped_renders_layer_3_only_chip(env: Environment) -> None:
    """`judge_skipped=True` surfaces the amber `layer-3 only` chip instead of llm-judged."""
    bd = _full_breakdown()
    bd["judge_skipped"] = True
    out = env.get_template("components/score_card.html").render(
        score=72,
        match_breakdown=bd,
    )
    assert "layer-3 only" in out
    assert "llm-judged" not in out


def test_size_compact_uses_smaller_circle(env: Environment) -> None:
    """`size=compact` propagates to score_circle (h-10 w-10)."""
    out = env.get_template("components/score_card.html").render(
        score=86,
        match_breakdown=_full_breakdown(),
        size="compact",
    )
    assert "h-10 w-10" in out


def test_size_hero_uses_larger_circle(env: Environment) -> None:
    """`size=hero` propagates to score_circle (h-24 w-24)."""
    out = env.get_template("components/score_card.html").render(
        score=86,
        match_breakdown=_full_breakdown(),
        size="hero",
    )
    assert "h-24 w-24" in out


def test_score_thresholds_drive_ring_color(env: Environment) -> None:
    """Score thresholds: emerald ≥80 / indigo ≥60 / amber ≥40 / rose <40."""
    bd = _full_breakdown()
    for score, expected_ring in [
        (92, "stroke-emerald-400"),
        (65, "stroke-indigo-400"),
        (45, "stroke-amber-400"),
        (20, "stroke-rose-400"),
    ]:
        out = env.get_template("components/score_card.html").render(score=score, match_breakdown=bd)
        assert expected_ring in out, f"expected {expected_ring} for score {score}"


def test_empty_match_breakdown_renders(env: Environment) -> None:
    """Score with no breakdown (unscored / pre-Phase 2 row) renders without crashing."""
    out = env.get_template("components/score_card.html").render(score=0, match_breakdown={})
    assert out
    assert "MATCH" in out
    assert "no per-dimension data" in out
