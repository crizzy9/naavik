"""Discover action bar — Review & apply CTA wiring (plan 77 / 0.4.0.03).

Closes 0.3.3.08a deferred wiring follow-up from PR #170.

Three things this file proves:
  1. `discover_action_bar.html` Review & apply button points at
     `/_fragments/apply/preview/by-job/<job_id>` with target `#apply-preview-slot`.
  2. The new `by-job` route resolves/creates a DRAFT Application and renders
     the same `apply_preview_card.html` partial the application-id route uses.
  3. The Discover queue mount point (`#apply-preview-slot`) is present.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from jinja2 import ChainableUndefined, Environment, FileSystemLoader

os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")


@pytest.fixture(scope="module")
def client() -> TestClient:
    from main import app

    return TestClient(app)


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


# ── M1: action bar template wiring ───────────────────────────────────


def test_action_bar_review_apply_points_at_apply_preview_by_job(env: Environment):
    """Review & apply button hx-get target is `/_fragments/apply/preview/by-job/<id>`."""
    html = env.get_template("components/discover_action_bar.html").render(job_id=42)
    assert 'hx-get="/_fragments/apply/preview/by-job/42"' in html, html
    assert 'hx-target="#apply-preview-slot"' in html
    # Old workspace-expand wiring is gone.
    assert "/_fragments/discover/expanded/" not in html
    assert "#discover-main" not in html


def test_discover_queue_mount_point_present(env: Environment):
    """The Discover queue partial renders `#apply-preview-slot` for swap target.

    Uses the same `_JOB` shape `tests/test_components.py` parametrizes over —
    enough keys to satisfy `swipe_card.html` + the score circle macro.
    """
    job = {
        "id": 42,
        "company": "Stripe",
        "company_initial": "S",
        "company_color": "bg-purple-600",
        "gradient_from": "from-indigo-600",
        "gradient_to": "to-purple-600",
        "role": "Senior ML Engineer",
        "team": "Atlas",
        "score": 86,
        "location": "San Francisco",
        "salary_range": "$240-290k",
        "work_mode": "Hybrid",
        "team_size": "team of 12",
        "visa_friendly": True,
        "posted_relative": "2h ago",
        "jd_bullets": ["5+ years"],
        "warm_intro_label": None,
        "tags": ["ai-ml"],
        "match_breakdown": {"ai-ml": 0.95},
        "match_overall": 0.86,
    }
    html = env.get_template("pages/_discover_queue.html").render(
        current_card=job,
        up_next=[],
        stuck_drafts=[],
        auto_apply_drafts=[],
        saved_count=0,
        filters_active=0,
    )
    assert 'id="apply-preview-slot"' in html, html


# ── M1: by-job route end-to-end ──────────────────────────────────────


def test_apply_preview_by_job_returns_preview_card_for_known_job(client: TestClient):
    """GET `/_fragments/apply/preview/by-job/{job_id}` renders the preview card."""
    # Job 101 is the seeded Stripe headline (UNSWIPED) per sample_data.JOBS.
    r = client.get(
        "/_fragments/apply/preview/by-job/101",
        cookies={"naavik_session": "fake-1"},
    )
    assert r.status_code == 200, f"got {r.status_code}: {r.text[:400]}"
    assert "Generate tailored bundle?" in r.text
    assert "Confirm submit" in r.text
    assert "Cancel" in r.text


def test_apply_preview_by_job_404_for_missing_job(client: TestClient):
    """Unknown job_id → 404 via the standard `_job_or_404` guard."""
    r = client.get(
        "/_fragments/apply/preview/by-job/999999",
        cookies={"naavik_session": "fake-1"},
    )
    assert r.status_code == 404
