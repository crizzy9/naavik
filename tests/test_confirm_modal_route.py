"""Tests for the `/_modal/confirm` fragment route.

Plan 08 acceptance:
- Query-param round-trip works (title / message / action / label / tone / method).
- Missing required param → 422.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.uses_sample_data_shims


def _client() -> TestClient:
    from main import app

    return TestClient(app, raise_server_exceptions=True)


def test_confirm_modal_query_param_roundtrip() -> None:
    c = _client()
    r = c.get(
        "/_modal/confirm",
        params={
            "title": "Delete bullet",
            "message": "This can't be undone.",
            "action": "/api/v1/bullets/42",
            "label": "Delete",
            "tone": "danger",
            "method": "delete",
        },
    )
    assert r.status_code == 200
    body = r.text
    assert "<dialog" in body
    assert "Delete bullet" in body
    assert "This can&#39;t be undone." in body or "This can't be undone." in body
    assert 'hx-delete="/api/v1/bullets/42"' in body
    # Confirm + cancel labels — strip whitespace differences.
    collapsed = " ".join(body.split())
    assert ">Delete<" in collapsed or "Delete </button>" in collapsed
    assert ">Cancel<" in collapsed or "Cancel </button>" in collapsed


def test_confirm_modal_warning_tone() -> None:
    c = _client()
    r = c.get(
        "/_modal/confirm",
        params={
            "title": "Discard?",
            "message": "Unsaved edits.",
            "action": "/profile",
            "label": "Discard",
            "tone": "warning",
            "method": "post",
        },
    )
    assert r.status_code == 200
    assert "bg-amber-500" in r.text


def test_confirm_modal_missing_required_param_returns_422() -> None:
    c = _client()
    r = c.get("/_modal/confirm", params={"title": "Just title"})
    assert r.status_code == 422


def test_confirm_modal_invalid_tone_returns_422() -> None:
    c = _client()
    r = c.get(
        "/_modal/confirm",
        params={
            "title": "T",
            "message": "M",
            "action": "/x",
            "tone": "rainbow",
        },
    )
    assert r.status_code == 422
