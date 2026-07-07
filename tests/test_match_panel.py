"""Match panel (components/discover/match_panel.html + requirement matching)."""

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


def test_persisted_coverage_wins_over_heuristic():
    """A fresh `requirements_coverage` blob (scorer.match_analysis) drives
    the marks — the token heuristic would leave this seniority ask unmarked."""
    from services.scorer.match_analysis import criteria_hash

    criteria = ["Senior software engineering experience", "Rust systems programming"]
    out = match_requirements(
        criteria,
        [],
        [],
        requirements_coverage={
            "criteria_hash": criteria_hash(criteria),
            "covered": [True, False],
        },
    )
    assert [r["matched"] for r in out] == [True, False]


def test_stale_coverage_hash_falls_back_to_heuristic():
    """Coverage computed against an older criteria list (JD re-extracted)
    must not misalign marks — hash mismatch → heuristic."""
    out = match_requirements(
        ["Experience with backend systems"],
        [],
        ["backend"],
        requirements_coverage={"criteria_hash": "deadbeef00000000", "covered": [False]},
    )
    assert out[0]["matched"] is True  # heuristic tag match, stale blob ignored


@pytest.mark.uses_sample_data_shims
def test_review_page_renders_match_panel():
    from db import sample_data as sd
    from main import app as fastapi_app

    client = TestClient(fastapi_app, raise_server_exceptions=True)
    job = sd.JOBS[0]
    r = client.get(f"/discover/{job.id}", cookies={"naavik_session": "fake-1"})
    assert r.status_code == 200
    assert 'data-testid="match-panel"' in r.text
    # 2026-07 round 2: WHAT THEY WANT restored as the JD-requirements
    # column (with coverage marks) next to the judge's two verdict columns.
    assert "WHAT THEY WANT" in r.text
    assert 'data-testid="match-what-they-want"' in r.text
    assert "YOUR STRENGTHS" in r.text
    assert "WHAT&#39;S MISSING" in r.text or "WHAT'S MISSING" in r.text
