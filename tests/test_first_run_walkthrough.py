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


def test_signup_disabled_renders_signup_form_with_banner(client: TestClient, monkeypatch):
    """Plan 0.7.0.47 (2026-05-24, supersedes 0.7.0.45 UI fix): when
    `_compute_signup_disabled` returns True AND operator hits
    `/login?mode=signup`, the SIGNUP FORM renders alongside the amber
    banner explaining the gate. The 0.7.0.45 "render signin form
    instead" rewrite removed the operator's ability to attempt signup
    from the UI; this plan restores explicit-intent honoring.

    The form's API endpoint will 403 if the gate actually fires
    (`src/api/auth.py:218`), but the operator gets an inline error card
    via `hx-target-error="#login-card"` — not a silent demotion to a
    different page.
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
    # Signup form renders — operator's `?mode=signup` intent is honored.
    assert 'hx-post="/api/v1/auth/signup"' in body
    # Not the signin form.
    assert 'hx-post="/api/v1/auth/login"' not in body


def test_signup_disabled_renders_create_account_header(client: TestClient, monkeypatch):
    """Plan 0.7.0.47 (2026-05-24, replaces 0.7.0.45's stale
    `_renders_welcome_back_header`): when `signup_disabled` fires on
    `?mode=signup`, `is_signup` stays True (per plan 0.7.0.47 — the
    operator's explicit intent is honored). Heading reads "Create your
    account", submit button reads "Create account", SSO info card is
    suppressed (signin-only), and the "Already have an account? Sign
    in" footer link covers the misclick-recovery case the 0.7.0.45 fix
    was originally targeting.
    """
    from ui.routes import auth as auth_routes

    async def _disabled(session):
        return True

    monkeypatch.setattr(auth_routes, "_compute_signup_disabled", _disabled)
    r = client.get("/login?mode=signup")
    body = r.text
    assert "Create your account" in body
    assert "Welcome back" not in body
    # Submit button text mirrors signup mode.
    assert "Create account</span>" in body or ">Create account<" in body
    # SSO info card renders only in signin mode — suppressed here.
    assert "SSO coming soon" not in body
    # Alt-mode CTA points BACK to /login signin — misclick recovery.
    assert "Already have an account?" in body


def test_signup_disabled_banner_carries_setup_help_link(client: TestClient, monkeypatch):
    """Plan 0.7.0.47 (2026-05-24): the amber `signup_disabled` banner
    MUST link to `/setup-help` so operators who lost their credentials
    have a discoverable recovery path (Recipe 3 — wipe `.naavik/db`).
    Without this link the operator has no escape from the gate other
    than going to `psql` directly, which they can't be expected to know.
    """
    from ui.routes import auth as auth_routes

    async def _disabled(session):
        return True

    monkeypatch.setattr(auth_routes, "_compute_signup_disabled", _disabled)
    r = client.get("/login?mode=signup")
    body = r.text
    assert "data-signup-disabled-banner" in body
    # Recovery affordance inline in the banner body.
    assert 'href="/setup-help"' in body, (
        "signup_disabled banner missing /setup-help link — operators who "
        "lost credentials have no recovery path from the /login surface"
    )


def test_signup_disabled_create_account_link_visible_on_signin_default(
    client: TestClient, monkeypatch
):
    """Plan 0.7.0.47 (2026-05-24, reverses 0.7.0.45's `elif not
    signup_disabled` hide): `GET /login` (no mode param) MUST render
    the "First time? Create account" alt-mode CTA even when signup is
    disabled, so the operator has a discoverable path to signup mode.
    The signup page itself explains the gate via the amber banner.

    The 0.7.0.45 hide removed agency — operators saw the signin form
    and had no UI affordance to even ATTEMPT signup or discover the
    recovery flow.
    """
    from ui.routes import auth as auth_routes

    async def _disabled(session):
        return True

    monkeypatch.setattr(auth_routes, "_compute_signup_disabled", _disabled)
    r = client.get("/login")
    assert r.status_code == 200
    body = r.text
    # Default signin surface — banner is suppressed (no _requested_signup).
    assert "data-signup-disabled-banner" not in body
    # Alt-mode CTA visible — operator can navigate to signup mode.
    assert "First time?" in body
    assert 'href="/login?mode=signup"' in body
    # Still the signin form (mode default).
    assert 'hx-post="/api/v1/auth/login"' in body


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
