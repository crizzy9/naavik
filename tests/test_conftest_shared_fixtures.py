"""Smoke test for the shared client/auth/CSRF fixtures (plan 91 Phase 0.3)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.uses_sample_data_shims


def test_plain_client_serves_login(client):
    assert client.get("/login").status_code == 200


def test_authed_client_serves_overview(authed_client):
    # `/` (overview) is behind require_authed_session; the fake-session cookie
    # + NAAVIK_DEBUG makes it resolve to the seeded owner.
    assert authed_client.get("/").status_code == 200


def test_csrf_headers_match_cookie(csrf_headers, csrf_token, auth_cookies):
    assert csrf_headers["X-CSRF-Token"] == csrf_token
    assert auth_cookies["naavik_csrf"] == csrf_token
    assert auth_cookies["naavik_session"] == "fake-1"
