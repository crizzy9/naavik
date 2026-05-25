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

pytestmark = pytest.mark.uses_sample_data_shims


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
    """When `_compute_signup_disabled` returns True → amber banner renders
    AND the signin form is rendered alongside (plan 0.7.0.45 — the
    original "banner-only, no form" UX was a dead-end; operator who
    clicked "Create account" by mistake had no signin form to fall back
    to without navigating away).
    """
    from ui.routes import auth as auth_routes

    async def _disabled(session):
        return True

    monkeypatch.setattr(auth_routes, "_compute_signup_disabled", _disabled)
    r = client.get("/login?mode=signup")
    assert r.status_code == 200
    body = r.text
    # The amber banner explains why signup is gated.
    assert "data-signup-disabled-banner" in body
    assert "This instance already has an account." in body
    # The signin form is rendered immediately below the banner —
    # operator can sign in without navigating away.
    assert 'hx-post="/api/v1/auth/login"' in body
    # No signup form (would 403 anyway).
    assert 'hx-post="/api/v1/auth/signup"' not in body


def test_signup_disabled_renders_welcome_back_header(client: TestClient, monkeypatch):
    """Plan 0.7.0.45: when signup_disabled fires on `?mode=signup`, the
    template's `is_signup` flag is rewritten to False so the header
    reads "Welcome back" (not "Create your account") + the submit button
    reads "Sign in" (not "Create account") + the SSO info card renders.
    Heading/button/CTA stay coherent with the signin form rendered below
    the banner.
    """
    from ui.routes import auth as auth_routes

    async def _disabled(session):
        return True

    monkeypatch.setattr(auth_routes, "_compute_signup_disabled", _disabled)
    r = client.get("/login?mode=signup")
    body = r.text
    assert "Welcome back" in body
    assert "Create your account" not in body
    # Submit button text mirrors signin mode.
    assert "Sign in</span>" in body or ">Sign in<" in body
    # SSO info card renders only in signin mode.
    assert "SSO coming soon" in body
    # "First time? Create account" CTA is hidden when signup is disabled
    # (clicking it would just bounce back to this same banner).
    assert "First time?" not in body


def test_setup_help_link_path_matches_route(client: TestClient):
    """`/setup-help` resolves via the registered route name."""
    from main import app

    # The route is registered.
    route_paths = {r.path for r in app.routes if hasattr(r, "path")}
    assert "/setup-help" in route_paths


def test_login_form_has_hx_target_error_for_4xx_swap(client: TestClient):
    """Plan 0.7.0.39: HTMX 2.x ignores 4xx/5xx responses by default; the
    signup/login form must declare `hx-target-error` (via the
    `response-targets` extension already loaded in base.html) so 422
    password-complexity errors swap into the login-card region instead of
    silently dropping. Pin both signup and signin modes.
    """
    for mode in ("signup", "signin"):
        r = client.get(f"/login?mode={mode}")
        assert r.status_code == 200
        body = r.text
        assert 'hx-target-error="#login-card"' in body, (
            f"login form ({mode} mode) missing hx-target-error; HTMX would "
            f"silently drop 4xx responses from the signup/login endpoint"
        )
