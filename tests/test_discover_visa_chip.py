"""Discover swipe-card visa chip — plan 65 § D.1.

When `Job.match_breakdown.visa_concern = True` (set by the orchestrator
on visa zero-out), the swipe card renders a `VISA · sponsorship blocked`
chip. Test verifies the discover_ctx threading + the rendered template
fragment.
"""

from __future__ import annotations

import os  # noqa: I001

os.environ.setdefault("NAAVIK_DEBUG", "1")

from types import SimpleNamespace  # noqa: E402

import pytest
from jinja2 import Environment, FileSystemLoader  # noqa: E402

from ui.discover_ctx import swipe_card_dict  # noqa: E402

pytestmark = pytest.mark.uses_sample_data_shims


def _job_with_breakdown(visa_concern: bool):
    return SimpleNamespace(
        id=1,
        company="Acme",
        role="Staff SWE",
        team=None,
        location="SF · Hybrid",
        salary_min=None,
        salary_max=None,
        score=0.0 if visa_concern else 0.86,
        found_at=None,
        posted_at=None,
        criteria=None,
        tags=["ai-ml"],
        match_breakdown={"visa_concern": visa_concern},
        visa_restrictions=None,
        apply_url=None,
        apply_kind=None,
    )


def test_swipe_card_dict_threads_visa_concern_true():
    j = _job_with_breakdown(visa_concern=True)
    out = swipe_card_dict(j)
    assert out["visa_concern"] is True


def test_swipe_card_dict_threads_visa_concern_false_default():
    j = _job_with_breakdown(visa_concern=False)
    out = swipe_card_dict(j)
    assert out["visa_concern"] is False


def test_swipe_card_dict_missing_breakdown_defaults_false():
    """No `match_breakdown` payload at all → visa_concern stays False."""
    j = _job_with_breakdown(visa_concern=False)
    j.match_breakdown = None
    out = swipe_card_dict(j)
    assert out["visa_concern"] is False


def test_swipe_card_template_renders_visa_chip_when_true():
    """End-to-end template render — `VISA · sponsorship blocked` is in HTML."""
    env = Environment(
        loader=FileSystemLoader("src/ui/templates"),
        autoescape=True,
    )
    # The swipe_card depends on _macros — Jinja resolves cross-imports via loader.
    template = env.get_template("components/swipe_card.html")
    job = swipe_card_dict(_job_with_breakdown(visa_concern=True))
    html = template.render(job=job)
    assert "VISA · sponsorship blocked" in html


def test_swipe_card_template_omits_visa_chip_when_false():
    env = Environment(
        loader=FileSystemLoader("src/ui/templates"),
        autoescape=True,
    )
    template = env.get_template("components/swipe_card.html")
    job = swipe_card_dict(_job_with_breakdown(visa_concern=False))
    html = template.render(job=job)
    assert "VISA · sponsorship blocked" not in html
