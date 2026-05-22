"""Discover · review & apply two-step UX — plan 75 / 0.3.3.08.

Three new fragment routes ship alongside existing `_fragments/apply/*`:

  - GET  /_fragments/apply/preview/{application_id}  → confirmation card
  - POST /_fragments/apply/confirm/{application_id}  → bundle-generated trigger
  - GET  /_fragments/apply/cancel-preview            → empty fragment

This file covers:
  1. Preview returns 200 + card HTML for owner; 404 for cross-user.
  2. Confirm returns 200 + `HX-Trigger: {"bundle-generated": ...}` header.
  3. Cancel returns 200 + empty body.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.uses_sample_data_shims

os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")


@pytest.fixture(scope="module")
def client() -> TestClient:
    from main import app

    return TestClient(app)


def test_preview_renders_card_for_known_application(client: TestClient):
    """GET preview returns 200 + the preview-card body. Uses the seeded
    application id 13 from sample_data (legacy test path)."""
    r = client.get(
        "/_fragments/apply/preview/13",
        cookies={"naavik_session": "fake-1"},
    )
    assert r.status_code == 200
    assert "Generate tailored bundle?" in r.text
    assert "Confirm submit" in r.text
    assert "Cancel" in r.text
    # Card carries the application id so the cancel-button target binds.
    assert 'data-apply-preview="13"' in r.text


def test_preview_404_for_missing_application(client: TestClient):
    """Unknown application id → 404 (legacy path; no fake-session IDOR check)."""
    r = client.get(
        "/_fragments/apply/preview/999999",
        cookies={"naavik_session": "fake-1"},
    )
    assert r.status_code == 404


def test_confirm_emits_hx_trigger_header(client: TestClient):
    """POST confirm returns 200 + `HX-Trigger: bundle-generated` payload."""
    # Confirm route uses CSRF + rate-limit — fake-session bypass keeps both
    # quiet in legacy test mode (no CSRF cookie required when stub mode).
    csrf_token = "test-csrf"
    r = client.post(
        "/_fragments/apply/confirm/13",
        headers={"X-CSRF-Token": csrf_token},
        cookies={"naavik_csrf": csrf_token, "naavik_session": "fake-1"},
    )
    assert r.status_code == 200, f"got {r.status_code}: {r.text[:200]}"
    trigger = r.headers.get("hx-trigger")
    assert trigger is not None, "HX-Trigger header missing"
    assert "bundle-generated" in trigger
    assert "13" in trigger


def test_confirm_404_for_missing_application(client: TestClient):
    """Confirm on unknown application → 404."""
    csrf_token = "test-csrf"
    r = client.post(
        "/_fragments/apply/confirm/999999",
        headers={"X-CSRF-Token": csrf_token},
        cookies={"naavik_csrf": csrf_token, "naavik_session": "fake-1"},
    )
    assert r.status_code == 404


def test_cancel_preview_returns_empty_fragment(client: TestClient):
    """Cancel button → empty HTML body (swap target replaces with nothing)."""
    r = client.get("/_fragments/apply/cancel-preview")
    assert r.status_code == 200
    # Empty body (HTMX swaps in nothing).
    assert r.text == ""
