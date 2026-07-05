"""Application mutation route IDOR boundary — plan 85 / 0.4.0.21 (MED).

PR #191 hacker MED identified that the 4 mutation handlers on
`/api/v1/applications/*` (submit / discard / put_status / move) fetched
by bare `application_id` with no `Application.user_id == current_user.id`
boundary. This file pins the fix at the route layer (each handler now
calls `svc.get_application` then checks ownership before calling the
service-layer mutation) and verifies the boundary holds for cross-user
requests.

Mirrors the postmortem-IDOR pattern in `test_ats_postmortem.py::
test_retrieve_owner_only_idor` — a User-B request for User-A's row
returns 404 (no existence leak; cannot enumerate IDs).
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.uses_sample_data_shims

os.environ.setdefault("NAAVIK_DEBUG", "1")
os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")


_MATCHING_CSRF = "matching-csrf-token-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


@pytest.fixture
def client_with_user():
    """Spin up TestClient with require_password_complete overridden to user id=42."""
    from fastapi.testclient import TestClient

    from main import app
    from services.auth import require_password_complete

    user = SimpleNamespace(id=42, is_active=True, must_change_password=False)

    async def _override():
        return user

    app.dependency_overrides[require_password_complete] = _override
    # Routes now require CSRF (plan 91 Phase 1.6); thread a matching double-submit pair.
    _c = TestClient(app, raise_server_exceptions=True, headers={"X-CSRF-Token": "t"})
    _c.cookies.set("naavik_csrf", "t")
    yield _c, user
    app.dependency_overrides.pop(require_password_complete, None)


def _foreign_app(application_id: int = 99, owner_id: int = 1) -> SimpleNamespace:
    """Build a SimpleNamespace stub for an Application owned by another user."""
    return SimpleNamespace(
        id=application_id,
        user_id=owner_id,
        status="DRAFT",
        deleted_at=None,
    )


def test_submit_cross_user_returns_404(client_with_user):
    """POST /api/v1/applications/{id}/submit — User B targeting User A's app → 404.

    No leakage: same shape as a missing-application response, so an
    attacker cannot enumerate which IDs exist.
    """
    client, user = client_with_user
    other = _foreign_app(application_id=99, owner_id=1)
    with patch("api.applications.svc.get_application", new=AsyncMock(return_value=other)):
        r = client.post("/api/v1/applications/99/submit")
    assert r.status_code == 404
    assert "Application not found" in r.text


def test_discard_cross_user_returns_404(client_with_user):
    """DELETE /api/v1/applications/{id}/discard — User B → 404 on User A's app."""
    client, user = client_with_user
    other = _foreign_app(application_id=77, owner_id=1)
    with patch("api.applications.svc.get_application", new=AsyncMock(return_value=other)):
        r = client.delete("/api/v1/applications/77/discard")
    assert r.status_code == 404
    assert "Application not found" in r.text


def test_put_status_cross_user_returns_404(client_with_user):
    """PUT /api/v1/applications/{id}/status — User B → 404 on User A's app.

    Cross-user check fires BEFORE payload validation, so a malformed
    payload from a cross-user attacker also surfaces as 404 (not 422)
    — preserves the no-enumeration property.
    """
    client, user = client_with_user
    other = _foreign_app(application_id=55, owner_id=1)
    with patch("api.applications.svc.get_application", new=AsyncMock(return_value=other)):
        r = client.put(
            "/api/v1/applications/55/status",
            json={"status": "RECRUITER_SCREEN"},
        )
    assert r.status_code == 404
    assert "Application not found" in r.text


def test_move_cross_user_returns_404(client_with_user):
    """POST /api/v1/applications/move — User B → 404 on User A's app.

    The move route accepts an `application_id` in the payload (not the
    URL path); IDOR check still fires once the ID is resolved.
    """
    client, user = client_with_user
    other = _foreign_app(application_id=33, owner_id=1)
    with patch("api.applications.svc.get_application", new=AsyncMock(return_value=other)):
        r = client.post(
            "/api/v1/applications/move",
            json={"application_id": 33, "target_status": "RECRUITER_SCREEN"},
        )
    assert r.status_code == 404
    assert "Application not found" in r.text


def test_submit_missing_app_also_returns_404(client_with_user):
    """Defensive: missing-app (svc.get_application → None) returns the same 404.

    Same 404 shape as the cross-user case is the no-enumeration
    invariant — an attacker probing IDs cannot distinguish
    "doesn't exist" from "exists but is not mine".
    """
    client, _ = client_with_user
    with patch("api.applications.svc.get_application", new=AsyncMock(return_value=None)):
        r = client.post("/api/v1/applications/9999/submit")
    assert r.status_code == 404
    assert "Application not found" in r.text


def test_submit_owner_passes_idor_then_calls_service(client_with_user):
    """Positive case — owner's submit reaches `submit_draft` (legitimate flow unbroken).

    Asserts: IDOR check passes when ownership matches → the service-layer
    call IS made → test verifies via the side-effect (we patch submit_draft
    to track the call). The actual submit_draft behavior is exercised in
    test_application_service.py; here we only care that the IDOR check
    doesn't accidentally block legitimate same-user requests.
    """
    client, user = client_with_user
    owned = SimpleNamespace(id=11, user_id=user.id, status="DRAFT", board=None, deleted_at=None)
    # Mock submit_draft to raise ValidationError so the request returns 409
    # (deterministic, no need to wire the full submission pipeline).
    from services.applications import ValidationError

    submit_mock = AsyncMock(side_effect=ValidationError("no_board", code="no_board"))
    with (
        patch("api.applications.svc.get_application", new=AsyncMock(return_value=owned)),
        patch("api.applications.svc.submit_draft", new=submit_mock),
    ):
        r = client.post("/api/v1/applications/11/submit")
    # Not 404 → IDOR check passed → submit_draft was reached → returned 409.
    assert r.status_code == 409
    submit_mock.assert_awaited_once()
