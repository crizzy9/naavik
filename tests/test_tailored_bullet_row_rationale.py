"""Unit tests for the new `rationale` arg on `components/tailored_bullet_row.html`
(plan 72 / 0.3.2.02 — Variant A inline ledger).

Covers:
- legacy call sites (rationale omitted) render exactly as today (backward compat)
- selected=True + rationale.why_selected → cyan italic "why kept · ..." line
- selected=False + rationale.why_dropped → slate italic "why dropped · ..." line
- rationale set but matching `why_*` is null → no extra line
"""

from __future__ import annotations

import pytest
from jinja2 import ChainableUndefined, Environment, FileSystemLoader

from ui.templates_setup import STATUS_DOT_COLORS, TAG_VOCAB

pytestmark = pytest.mark.uses_sample_data_shims

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


_BULLET = {
    "id": 7,
    "text": "Built ML personalization platform; +23% homepage CTR.",
    "tags": ["ai-ml", "platform"],
}


def test_rationale_none_backward_compatible(env: Environment) -> None:
    """Legacy call without `rationale` arg renders identical to pre-plan-72."""
    out = env.get_template("components/tailored_bullet_row.html").render(
        bullet=_BULLET,
        selected=True,
        trimmed_line="Built ML personalization platform; +23% homepage CTR.",
        chips=["jd", "scale"],
    )
    # No rationale line at all.
    assert "why kept" not in out
    assert "why dropped" not in out
    # The bullet text + chips still render.
    assert "Built ML personalization platform" in out
    assert "# jd" in out


def test_rationale_selected_renders_cyan_why_kept(env: Environment) -> None:
    """Selected bullet + rationale.why_selected → cyan italic ledger line."""
    out = env.get_template("components/tailored_bullet_row.html").render(
        bullet=_BULLET,
        selected=True,
        trimmed_line="Built ML personalization platform; +23% homepage CTR.",
        chips=["jd", "scale"],
        rationale={
            "selected": True,
            "why_selected": "matches JD ai-ml + scale signals; quantified impact",
            "why_dropped": None,
        },
    )
    assert "why kept" in out
    assert "matches JD ai-ml + scale signals; quantified impact" in out
    # Cyan tone (`text-cyan-300`) signals AI-authored.
    assert "text-cyan-300" in out
    assert "border-cyan-400/40" in out
    # No "why dropped" line on selected bullets.
    assert "why dropped" not in out


def test_rationale_dropped_renders_slate_why_dropped(env: Environment) -> None:
    """Dropped bullet + rationale.why_dropped → slate italic ledger line."""
    out = env.get_template("components/tailored_bullet_row.html").render(
        bullet=_BULLET,
        selected=False,
        trimmed_line="Older role bullet that did not survive the JD filter.",
        chips=["older role"],
        rationale={
            "selected": False,
            "why_selected": None,
            "why_dropped": "duplicate signal of a later, stronger bullet",
        },
    )
    assert "why dropped" in out
    assert "duplicate signal of a later, stronger bullet" in out
    # Slate tone (muted) for dropped bullets.
    assert "text-slate-400" in out
    assert "border-slate-700" in out
    # No "why kept" line on dropped bullets.
    assert "why kept" not in out


def test_rationale_selected_without_why_selected_renders_no_ledger(env: Environment) -> None:
    """Selected bullet with null `why_selected` → no ledger line (graceful)."""
    out = env.get_template("components/tailored_bullet_row.html").render(
        bullet=_BULLET,
        selected=True,
        trimmed_line="Bullet text.",
        chips=["jd"],
        rationale={"selected": True, "why_selected": None, "why_dropped": None},
    )
    assert "why kept" not in out
    assert "why dropped" not in out


def test_rationale_dropped_without_why_dropped_renders_no_ledger(env: Environment) -> None:
    """Dropped bullet with null `why_dropped` → no ledger line."""
    out = env.get_template("components/tailored_bullet_row.html").render(
        bullet=_BULLET,
        selected=False,
        trimmed_line="Bullet text.",
        chips=["older role"],
        rationale={"selected": False, "why_selected": None, "why_dropped": None},
    )
    assert "why kept" not in out
    assert "why dropped" not in out


def test_rationale_cross_state_does_not_show_wrong_line(env: Environment) -> None:
    """A selected bullet whose rationale only carries `why_dropped` (cross-state
    accident) shows NEITHER line — guard prevents leak.
    """
    out = env.get_template("components/tailored_bullet_row.html").render(
        bullet=_BULLET,
        selected=True,
        trimmed_line="Bullet text.",
        chips=["jd"],
        rationale={
            "selected": True,
            "why_selected": None,
            "why_dropped": "should not show",
        },
    )
    assert "should not show" not in out
    assert "why dropped" not in out
    assert "why kept" not in out
