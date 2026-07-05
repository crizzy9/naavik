"""Discover action bar — Review & apply CTA wiring.

Pins the SCREENS.md § 7 wiring: Review & apply opens the job's review
workspace inline (`GET /_fragments/discover/expanded/<id>` into
`#discover-main`). The plan-75/77 preview-card cluster it replaced was
deleted in plan 91 (Q3); the negative assertions keep it from coming back.
"""

from __future__ import annotations

import pytest
from jinja2 import ChainableUndefined, Environment, FileSystemLoader

pytestmark = pytest.mark.uses_sample_data_shims


@pytest.fixture(scope="module")
def env() -> Environment:
    from ui.templates_setup import STATUS_DOT_COLORS, TAG_VOCAB

    e = Environment(
        loader=FileSystemLoader("src/ui/templates"),
        autoescape=True,
        undefined=ChainableUndefined,
    )
    e.globals["STATUS_DOT_COLORS"] = STATUS_DOT_COLORS
    e.globals["TAG_VOCAB"] = TAG_VOCAB
    return e


def test_action_bar_review_apply_opens_job_workspace_inline(env: Environment):
    """P3 — Review & apply opens THAT job's review workspace directly:
    `GET /_fragments/discover/expanded/<id>` swapped into `#discover-main`
    (SCREENS.md § 7 wiring). The plan-77 preview-card detour (which left
    the user on the queue) is gone."""
    html = env.get_template("components/discover/discover_action_bar.html").render(job_id=42)
    assert 'hx-get="/_fragments/discover/expanded/42"' in html, html
    assert 'hx-target="#discover-main"' in html
    # Old preview-card wiring is gone.
    assert "/_fragments/apply/preview/by-job/" not in html
    assert "#apply-preview-slot" not in html
