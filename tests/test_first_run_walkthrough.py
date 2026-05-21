"""Plan 71 (0.3.3.14): first-run walkthrough smoke tests.

Exercises the three surfaces an operator hits during first-time setup:

1. `/setup-help` is reachable without auth (the recovery page itself).
2. `/login` renders the signup form when no User row exists.
3. `/login` renders the amber signup-disabled banner when a User exists.
4. The signup form button posts to `/api/v1/auth/signup`.

A full live-DB walkthrough (signup → login → save → 401 on cookie drop)
is gated on `NAAVIK_LIVE_DB=1`; the smoke tests below stay DB-free via
the conftest service-layer stubs.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client() -> TestClient:
    from main import app

    return TestClient(app, raise_server_exceptions=True)


def test_setup_help_reachable_without_auth(client: TestClient):
    """The recovery surface itself does not require auth."""
    r = client.get("/setup-help")
    assert r.status_code == 200
    assert "Setup help" in r.text


def test_login_page_renders_signup_form_when_no_user(client: TestClient, monkeypatch):
    """When `_compute_signup_disabled` returns False → signup mode renders the form."""
    # `_compute_signup_disabled` reads via session.exec; with the conftest
    # noop session returning empty results, count=0 → signup_disabled=False.
    r = client.get("/login?mode=signup")
    assert r.status_code == 200
    body = r.text
    # Form posts to the signup endpoint.
    assert 'hx-post="/api/v1/auth/signup"' in body
    # Password hint visible (PC.6 complexity rules).
    assert "12 characters" in body
    # No amber "already has an account" banner.
    assert "data-signup-disabled-banner" not in body


def test_login_page_renders_signin_form_by_default(client: TestClient):
    """`GET /login` (no mode) shows the sign-in form."""
    r = client.get("/login")
    assert r.status_code == 200
    body = r.text
    assert 'hx-post="/api/v1/auth/login"' in body
    assert "Welcome back" in body


def test_signup_disabled_banner_when_user_exists(client: TestClient, monkeypatch):
    """When `_compute_signup_disabled` returns True → amber banner renders."""
    from ui.routes import auth as auth_routes

    async def _disabled(session):
        return True

    monkeypatch.setattr(auth_routes, "_compute_signup_disabled", _disabled)
    r = client.get("/login?mode=signup")
    assert r.status_code == 200
    body = r.text
    # The amber banner replaces the signup form.
    assert "data-signup-disabled-banner" in body
    # No signup form rendered.
    assert 'hx-post="/api/v1/auth/signup"' not in body


def test_setup_help_link_path_matches_route(client: TestClient):
    """`/setup-help` resolves via the registered route name."""
    from main import app

    # The route is registered.
    route_paths = {r.path for r in app.routes if hasattr(r, "path")}
    assert "/setup-help" in route_paths
