"""Unauthenticated-request redirect matrix on `require_authed_session`.

Plan 75 / 0.3.3.22 originally added `HX-Redirect` for HTMX UI requests; plan
0.7.0.39 (2026-05-21) widened the dep to also redirect browser top-nav
(non-HTMX, non-API) requests with a 307 + `Location` header. Without the
307, a fresh browser visit to `http://localhost:8000/` (no cookies) returned
a JSON 401 error page instead of redirecting to `/login`.

The matrix this file pins:

  1. HTMX UI request (HX-Request: true, path != `/api/v1/*`) → 401 +
     `HX-Redirect: /login`.
  2. API request (`/api/v1/...`) → 401 + NO redirect headers (SDK consumers
     shouldn't auto-follow redirects to HTML pages).
  3. Browser top-nav (no HX-Request, path != `/api/v1/*`) → 307 +
     `Location: /login`. This is the fresh-install path.
  4. HTMX request hitting `/api/v1/*` → bare 401 (API wins over HTMX hint).
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")


@pytest.fixture(scope="module")
def client() -> TestClient:
    from main import app

    return TestClient(app)


# A gated UI route that uses `require_authed_session` and serves HTML.
# `/api/v1/profile/full_name` for the API-path equivalent.
_API_PATH = "/api/v1/profile/full_name"


def test_htmx_ui_request_401_emits_hx_redirect_to_login(client: TestClient):
    """No cookie + HX-Request header → 401 + HX-Redirect: /login.

    HTMX clients always set the HX-Request header; the 401 body would
    otherwise be swapped into the page as a broken JSON fragment.
    """
    r = client.get(
        "/discover",
        headers={"HX-Request": "true"},
        cookies={},
        follow_redirects=False,
    )
    assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text[:200]}"
    assert r.headers.get("hx-redirect") == "/login"
    # Regression guard for the original bug: never reintroduce the dead
    # `/auth/login` URL.
    assert r.headers.get("hx-redirect") != "/auth/login"


def test_api_request_401_stays_bare(client: TestClient):
    """`/api/v1/...` 401 stays bare — no redirect headers."""
    r = client.put(
        _API_PATH,
        cookies={},
        data={"value": "New"},
    )
    assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text[:200]}"
    assert r.headers.get("hx-redirect") is None
    assert r.headers.get("location") is None


def test_browser_nav_request_redirects_to_login(client: TestClient):
    """Plain browser GET (no HX-Request header) on a gated UI route → 307 +
    Location: /login. This is the bug 0.7.0.39 fixed: prior behavior was a
    JSON 401 error page on `http://localhost:8000/` from a cookieless tab.
    """
    r = client.get("/discover", cookies={}, follow_redirects=False)
    assert r.status_code == 307, f"expected 307, got {r.status_code}: {r.text[:200]}"
    assert r.headers.get("location") == "/login"


def test_htmx_api_request_401_no_redirect(client: TestClient):
    """HTMX request hitting `/api/v1/*` → bare 401 (API path wins over HTMX hint)."""
    r = client.put(
        _API_PATH,
        cookies={},
        data={"value": "New"},
        headers={"HX-Request": "true"},
    )
    assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text[:200]}"
    assert r.headers.get("hx-redirect") is None
    assert r.headers.get("location") is None
