"""CSRF enforcement on the mutation surface (plan 91 Phase 1.6).

An authenticated caller with NO CSRF double-submit pair must be rejected (403)
on state-changing routes that previously accepted the request. Proves the
`require_csrf` additions actually gate, not just that the dependency is present.
The happy path (valid pair) is covered by the per-route test files.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.uses_sample_data_shims


def _authed_no_csrf() -> TestClient:
    from main import app

    client = TestClient(app, raise_server_exceptions=True)
    client.cookies.set("naavik_session", "fake-1")  # authed, but no CSRF cookie/header
    return client


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("POST", "/api/v1/contacts", {"name": "x"}),
        ("POST", "/api/v1/contacts/find", {"company": "x"}),
        ("POST", "/api/v1/outreach/skip", {}),
        ("POST", "/api/v1/outreach/send", {"message_id": 1}),
        ("POST", "/api/v1/outreach/draft", {"contact_id": 1, "intent": "follow_up"}),
        ("POST", "/api/v1/bullets/reorder", {"bullet_ids": [1]}),
        ("POST", "/api/v1/profile-answers/1/accept", {}),
    ],
)
def test_state_change_requires_csrf(method: str, path: str, body: dict):
    resp = _authed_no_csrf().request(method, path, json=body)
    assert resp.status_code == 403, (
        f"{method} {path} should 403 without CSRF, got {resp.status_code}"
    )
