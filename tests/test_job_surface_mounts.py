"""Plan 96c2 — the job surface's two mounts render ONE body.

Render-equivalence is the anti-drift pin (risk table: "one-template/
two-mounts drifts into page-vs-modal divergence"): the modal and the page
must produce byte-identical #job-surface-body markup for the same ctx.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.uses_sample_data_shims

from types import SimpleNamespace  # noqa: E402


def _fake_job(jid: int = 700, **kw: Any) -> SimpleNamespace:
    from models.enums import (
        ApplicationBoard,
        JobQueueState,
        JobSource,
        RemotePolicy,
        SeniorityLevel,
        VisaRestriction,
    )

    now = datetime.now(UTC)
    base = {
        "id": jid,
        "user_id": 1,
        "source": JobSource.LINKEDIN,
        "external_id": f"ln-{jid}",
        "board": ApplicationBoard.LINKEDIN,
        "url": f"https://linkedin.com/jobs/view/{jid}",
        "url_type": "ats",
        "apply_url": None,
        "apply_kind": None,
        "apply_resolved_at": None,
        "apply_resolved_via": None,
        "apply_resolve_attempts": 0,
        "apply_next_resolve_at": None,
        "company": "SurfaceCo",
        "role": "Staff Engineer",
        "team": None,
        "location": "Remote · USA",
        "remote_policy": RemotePolicy.REMOTE,
        "seniority_level": SeniorityLevel.SENIOR,
        "posted_at": None,
        "posted_at_text": None,
        "found_at": now,
        "description": "Build the surface.",
        "description_html": None,
        "description_extracted_at": None,
        "description_extraction_model": None,
        "criteria": [],
        "skills_required": [],
        "visa_restrictions": VisaRestriction.SPONSORSHIP_AVAILABLE,
        "salary_min": None,
        "salary_max": None,
        "equity_pct": None,
        "score": 0.9,
        "score_explanation": None,
        "match_breakdown": {},
        "queue_state": JobQueueState.UNSWIPED,
        "tags": [],
        "warm_intro_contact_id": None,
        "raw_meta": {},
        "last_scrape_run_id": None,
        "duplicate_of_id": None,
        "deleted_at": None,
        "created_at": now,
        "updated_at": now,
    }
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.fixture
def client(monkeypatch) -> TestClient:
    from main import app
    from services import jobs as job_service

    job = _fake_job()

    async def _get_job(session, job_id):
        return job if job_id == 700 else None

    monkeypatch.setattr(job_service, "get_job", _get_job)
    c = TestClient(app, raise_server_exceptions=True)
    c.cookies.set("naavik_session", "fake-1")
    return c


def _body(html: str) -> str:
    m = re.search(r'<div id="job-surface-body".*', html, re.S)
    assert m, "job-surface-body missing"
    # Trim to the balanced close by depth-counting divs.
    text = m.group(0)
    depth = 0
    for tag in re.finditer(r"<div\b|</div>", text):
        depth += 1 if tag.group(0) == "<div" else -1
        if depth == 0:
            return text[: tag.end()]
    raise AssertionError("unbalanced job-surface-body markup")


def test_modal_and_page_render_identical_bodies(client):
    page = client.get("/jobs/700")
    modal = client.get("/_modal/job/700")
    assert page.status_code == modal.status_code == 200
    assert _body(page.text) == _body(modal.text)


def test_page_mount_carries_chrome_modal_does_not(client):
    page = client.get("/jobs/700")
    modal = client.get("/_modal/job/700")
    assert "<html" in page.text
    assert "<html" not in modal.text
    assert 'data-testid="job-surface-modal"' in modal.text
    # No application in the shim env → pre-apply view, no expand-to-self loop.
    assert 'data-view="pre_apply"' in modal.text


def test_pre_apply_view_renders_job_concerns(client):
    r = client.get("/jobs/700")
    assert "Job description" in r.text
    assert "Build the surface." in r.text
    assert "Review &amp; apply" in r.text


def test_view_override_query_param(client):
    # No application exists → post_apply is impossible; override is clamped.
    r = client.get("/jobs/700?view=post_apply")
    assert 'data-view="pre_apply"' in r.text


def test_surface_fragment_returns_bare_body(client):
    r = client.get("/_fragments/job-surface/700")
    assert r.status_code == 200
    assert "<html" not in r.text
    assert 'id="job-surface-body"' in r.text


def test_missing_job_404s_all_mounts(client):
    assert client.get("/jobs/701").status_code == 404
    assert client.get("/_modal/job/701").status_code == 404
    assert client.get("/_fragments/job-surface/701").status_code == 404
