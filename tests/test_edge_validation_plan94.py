"""Plan 94 slice B (plan 91 § 7.4) — input validation at the Pydantic edge.

Malformed input must be a 422 at the route boundary, never a 500 from a
bare `int(...)` coercion or an asyncpg `StringDataRightTruncation` when an
oversize value reaches a VARCHAR(N) column:

- `POST /api/v1/outreach/draft` / `/send` took free-form dicts and called
  `int(payload.get(...))` — a non-numeric id crashed with ValueError.
- `PUT /api/v1/profile` (bulk) routed `email` straight into the
  `Profile.email VARCHAR(320)` column with no length/format guard.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.uses_sample_data_shims


@pytest.fixture(scope="module")
def client() -> TestClient:
    from main import app

    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture(scope="module")
def auth_cookies() -> dict[str, str]:
    return {"naavik_session": "fake-1"}


@pytest.fixture(autouse=True)
def _override_csrf():
    from api.auth import require_csrf
    from main import app

    def _csrf_pass() -> None:
        return None

    app.dependency_overrides[require_csrf] = _csrf_pass
    yield
    app.dependency_overrides.pop(require_csrf, None)


# ── outreach: typed bodies, non-numeric ids → 422 ───────────────────────


def test_outreach_draft_non_numeric_contact_id_is_422(client, auth_cookies):
    r = client.post(
        "/api/v1/outreach/draft",
        json={"contact_id": "abc"},
        cookies=auth_cookies,
    )
    assert r.status_code == 422, r.text


def test_outreach_draft_non_numeric_app_id_is_422(client, auth_cookies):
    r = client.post(
        "/api/v1/outreach/draft",
        json={"contact_id": 1, "app_id": "not-a-number"},
        cookies=auth_cookies,
    )
    assert r.status_code == 422, r.text


def test_outreach_send_non_numeric_message_id_is_422(client, auth_cookies):
    r = client.post(
        "/api/v1/outreach/send",
        json={"message_id": "xyz"},
        cookies=auth_cookies,
    )
    assert r.status_code == 422, r.text


def test_outreach_send_missing_id_still_404s(client, auth_cookies):
    """The old `payload.get("message_id", 0)` default mapped a missing id to
    a 404 lookup miss — preserved."""
    r = client.post("/api/v1/outreach/send", json={}, cookies=auth_cookies)
    assert r.status_code == 404, r.text


# ── profile bulk PUT: email edge guard → 422, not asyncpg 500 ────────────


def test_bulk_put_oversize_email_is_422_not_500(client, auth_cookies):
    oversize = ("x" * 320) + "@example.com"  # > VARCHAR(320)
    r = client.put("/api/v1/profile", data={"email": oversize}, cookies=auth_cookies)
    assert r.status_code == 422, r.text
    assert "email" in r.text


def test_bulk_put_email_without_at_sign_is_422(client, auth_cookies):
    r = client.put("/api/v1/profile", data={"email": "not-an-email"}, cookies=auth_cookies)
    assert r.status_code == 422, r.text
    assert "email" in r.text


def test_bulk_put_valid_email_still_saves(client, auth_cookies):
    from db import sample_data as sd

    original = sd.PROFILE.email
    try:
        r = client.put(
            "/api/v1/profile",
            data={"email": "owner@example.com"},
            cookies=auth_cookies,
        )
        assert r.status_code == 200, r.text
    finally:
        sd.PROFILE.email = original


def test_bulk_put_empty_email_allowed(client, auth_cookies):
    """Clearing the field stays legal (empty string is not format-checked)."""
    from db import sample_data as sd

    original = sd.PROFILE.email
    try:
        r = client.put("/api/v1/profile", data={"email": ""}, cookies=auth_cookies)
        assert r.status_code == 200, r.text
    finally:
        sd.PROFILE.email = original
