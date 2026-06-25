"""Plan 71 (0.3.3.14) + plan 0.7.0.48: first-run walkthrough smoke tests.

Exercises the surfaces an operator hits during first-time setup:

1. `/setup-help` is reachable without auth (the recovery page itself).
2. `/login` renders the signin form by default.
3. The signup form posts to `/api/v1/auth/signup` and is always renderable
   on `/login?mode=signup` (no gating per plan 0.7.0.48).

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


def test_login_page_renders_signup_form_when_no_user(client: TestClient):
    """`/login?mode=signup` renders the signup form unconditionally (plan 0.7.0.48)."""
    r = client.get("/login?mode=signup")
    assert r.status_code == 200
    body = r.text
    # Form posts to the signup endpoint.
    assert 'hx-post="/api/v1/auth/signup"' in body
    # Password hint visible (PC.6 complexity rules; min-length lowered
    # to 8 in plan 0.7.0.48 Wave 2).
    assert "8 characters" in body
    # No signup-disabled banner anywhere (deleted in plan 0.7.0.48).
    assert "data-signup-disabled-banner" not in body


def test_login_page_renders_signin_form_by_default(client: TestClient):
    """`GET /login` (no mode) shows the sign-in form."""
    r = client.get("/login")
    assert r.status_code == 200
    body = r.text
    assert 'hx-post="/api/v1/auth/login"' in body
    assert "Welcome back" in body


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
