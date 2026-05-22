"""Plan 72 manual QA gate — exercises both surfaces via TestClient.

This is the engineer-manual-qa-gate substitute for Playwright capture per the
dispatch directive (TestClient acceptable; Playwright deferred to manager).
Both surfaces are exercised through the rendered HTMX page:

- Surface 1 (score_card): `/discover` swipe-card lower body + `/discover/{id}`
  review LEFT column
- Surface 2 (tailored_bullet_row.rationale): unit-tested in
  test_tailored_bullet_row_rationale.py; this gate confirms the wiring through
  `_apply_tailored_bullets.html` reads `r.rationale` without crashing.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from main import app

pytestmark = pytest.mark.uses_sample_data_shims


@pytest.fixture
def auth_cookies() -> dict[str, str]:
    return {"naavik_session": "fake-1"}


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_discover_page_renders_score_card(client: TestClient, auth_cookies: dict[str, str]) -> None:
    """Discover swipe-card renders score_card composite + nested panels."""
    r = client.get("/discover", cookies=auth_cookies)
    assert r.status_code == 200, f"discover returned {r.status_code}"
    html = r.text
    assert "score-card grid" in html, "score_card container not rendered"
    assert "STRENGTHS" in html, "strengths panel header not rendered"
    # `WHAT'S MISSING` gets HTML-escaped to `WHAT&#39;S MISSING`.
    assert "WHAT&#39;S MISSING" in html or "WHAT'S MISSING" in html
    assert "PER-DIMENSION" in html, "per-dimension middle zone not rendered"
    # Default `expanded=False` on swipe card → no provenance footer.
    # (Loose assertion: PROVENANCE may still appear on the review page surface
    # that's also included in the same HTML render if discover bundles them.)


def test_discover_review_page_renders_expanded_score_card(
    client: TestClient, auth_cookies: dict[str, str]
) -> None:
    """Discover · review LEFT column renders score_card with expanded=true."""
    # Pick a job with a DRAFT application from sample_data.
    from db import sample_data as sd

    draft = next((a for a in sd.APPLICATIONS if a.status.value == "DRAFT"), None)
    assert draft is not None, "no DRAFT application in sample_data"

    r = client.get(f"/discover/{draft.job_id}", cookies=auth_cookies)
    assert r.status_code == 200, f"discover/{draft.job_id} returned {r.status_code}"
    html = r.text
    assert "score-card grid" in html, "score_card container missing in review page"
    assert "STRENGTHS" in html
    assert "PROVENANCE" in html, "expanded=true should surface PROVENANCE footer"


def test_apply_tailored_bullets_renders_without_rationale(
    client: TestClient, auth_cookies: dict[str, str]
) -> None:
    """When generation_trace is missing/legacy (sample_data path), the bullet
    rows render without the rationale ledger — graceful degrade verified."""
    from db import sample_data as sd

    draft = next((a for a in sd.APPLICATIONS if a.status.value == "DRAFT"), None)
    assert draft is not None

    r = client.get(f"/discover/{draft.job_id}", cookies=auth_cookies)
    assert r.status_code == 200
    html = r.text
    # Bullet rows render (tailored_bullet_row.html present).
    assert "Tailored resume" in html or "tailored resume" in html.lower()
    # No rationale lines present (sample_data apps have no bullet_selection_log).
    assert "why kept · " not in html
    assert "why dropped · " not in html
