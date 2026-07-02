"""Match panel (components/match_panel.html + requirement matching)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ui.discover_review_ctx import match_requirements


def test_requirement_covered_by_matched_tags():
    out = match_requirements(
        ["Experience with backend systems"],
        [],
        ["backend"],
    )
    assert out[0]["matched"] is True


def test_requirement_covered_by_strength_token_overlap():
    out = match_requirements(
        ["Design and operate recommendation platforms at scale"],
        ["Built a recommendation platform serving 100M users"],
        [],
    )
    assert out[0]["matched"] is True


def test_requirement_not_covered_stays_honest():
    out = match_requirements(
        ["Active TS/SCI security clearance"],
        ["Built a recommendation platform"],
        ["backend"],
    )
    assert out[0]["matched"] is False


@pytest.mark.uses_sample_data_shims
def test_review_page_renders_match_panel():
    from db import sample_data as sd
    from main import app as fastapi_app

    client = TestClient(fastapi_app, raise_server_exceptions=True)
    job = sd.JOBS[0]
    r = client.get(f"/discover/{job.id}", cookies={"naavik_session": "fake-1"})
    assert r.status_code == 200
    assert 'data-testid="match-panel"' in r.text
    assert "WHAT THEY WANT" in r.text
    assert "YOUR STRENGTHS" in r.text
