"""Visa status chip render tests — plan 78 § D.6 (0.4.0.15).

Three visual states keyed off `Job.visa_restrictions` (VisaRestriction enum
string values): sponsors (cyan ok), no-sponsorship (rose warning) and unknown
(slate). Mounted between meta_items in `swipe_card.html`.
"""

from __future__ import annotations

import pytest
from jinja2 import ChainableUndefined, Environment, FileSystemLoader

pytestmark = pytest.mark.uses_sample_data_shims

_TEMPLATES_DIR = "src/ui/templates"


@pytest.fixture(scope="module")
def env() -> Environment:
    return Environment(
        loader=FileSystemLoader(_TEMPLATES_DIR),
        autoescape=True,
        undefined=ChainableUndefined,
    )


def _render(env: Environment, restriction: str | None, **kwargs) -> str:
    tpl = env.get_template("components/visa_status_chip.html")
    return tpl.render(restriction=restriction, **kwargs)


def test_visa_chip_renders_sponsors_state_for_sponsorship_available(env):
    out = _render(env, "sponsorship_available")
    assert "sponsors" in out.lower()
    # Cyan-tone classes present.
    assert "bg-cyan-500/15" in out
    assert "check-circle-2" in out
    assert 'data-visa-chip="sponsorship_available"' in out


def test_visa_chip_renders_warning_state_for_us_citizen_only(env):
    out = _render(env, "us_citizen_only")
    assert "no sponsorship" in out.lower()
    assert "bg-rose-500/15" in out
    assert "alert-triangle" in out
    assert 'data-visa-chip="us_citizen_only"' in out


def test_visa_chip_renders_warning_state_for_green_card_required(env):
    out = _render(env, "green_card_required")
    assert "no sponsorship" in out.lower()
    assert "bg-rose-500/15" in out
    assert 'data-visa-chip="green_card_required"' in out


def test_visa_chip_renders_unknown_state_for_not_mentioned(env):
    out = _render(env, "not_mentioned")
    assert "visa unknown" in out.lower()
    assert "bg-slate-700/40" in out
    assert "circle-help" in out
    assert 'data-visa-chip="not_mentioned"' in out


def test_visa_chip_compact_mode_drops_icon(env):
    out_full = _render(env, "sponsorship_available", compact=False)
    out_compact = _render(env, "sponsorship_available", compact=True)
    # Icon present only in full mode.
    assert 'data-lucide="check-circle-2"' in out_full
    assert 'data-lucide="check-circle-2"' not in out_compact
    # Label still present in compact mode.
    assert "sponsors" in out_compact.lower()


def test_visa_chip_uppercase_label_styling(env):
    """Label styling uses font-mono uppercase tracking-wide per chip conventions."""
    out = _render(env, "sponsorship_available")
    assert "font-mono" in out
    assert "uppercase" in out


def test_swipe_card_mounts_visa_chip(env):
    """swipe_card.html includes visa_status_chip when `job.visa_restriction` is set."""
    job_dict = {
        "id": 1,
        "company": "Anthropic",
        "company_initial": "A",
        "company_color": "bg-orange-600",
        "gradient_from": "from-orange-600",
        "gradient_to": "to-amber-600",
        "role": "Senior Backend Engineer",
        "team": "Infra",
        "score": 91,
        "unscored": False,
        "location": "Remote",
        "salary_range": "$240-300k",
        "work_mode": "Remote",
        "posted_relative": "2d ago",
        "jd_bullets": ["Build infra"],
        "warm_intro_label": None,
        "tags": ["backend"],
        "match_breakdown": {},
        "match_overall": 0.91,
        "visa_friendly": True,
        "visa_concern": False,
        "visa_restriction": "sponsorship_available",
        "strengths": [],
        "gaps": [],
        "visa_note": None,
    }
    tpl = env.get_template("components/swipe_card.html")
    out = tpl.render(job=job_dict, dimmed=False, swiping_dir=None)
    # visa_status_chip included → sentinel attribute present.
    assert 'data-visa-chip="sponsorship_available"' in out
    # Legacy `visa_friendly` meta_item should NOT appear (replaced by chip).
    assert 'data-lucide="user-check"' not in out


def test_swipe_card_omits_visa_chip_when_restriction_absent(env):
    """When `visa_restriction` is None (legacy data path), chip is suppressed."""
    job_dict = {
        "id": 1,
        "company": "Anthropic",
        "company_initial": "A",
        "company_color": "bg-orange-600",
        "gradient_from": "from-orange-600",
        "gradient_to": "to-amber-600",
        "role": "Senior Backend Engineer",
        "team": None,
        "score": 75,
        "unscored": False,
        "location": "Remote",
        "salary_range": None,
        "work_mode": "Remote",
        "posted_relative": "1d ago",
        "jd_bullets": [],
        "warm_intro_label": None,
        "tags": [],
        "match_breakdown": {},
        "match_overall": 0.75,
        "visa_friendly": False,
        "visa_concern": False,
        "visa_restriction": None,
        "strengths": [],
        "gaps": [],
        "visa_note": None,
    }
    tpl = env.get_template("components/swipe_card.html")
    out = tpl.render(job=job_dict, dimmed=False, swiping_dir=None)
    assert "data-visa-chip" not in out
