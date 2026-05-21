"""401 HX-Redirect refinement on `require_authed_session` — plan 75 / 0.3.3.22.

Currently the four 401 raise sites (`Not authenticated`, `Session expired`,
`Session revoked`, `Account disabled`) returned a bare 401 with no
HX-Redirect header. For HTMX clients (`HX-Request: true`) this surfaces a
broken inline fragment rather than navigating to `/auth/login`. This file
pins:

  1. HTMX UI request (HX-Request: true, path != `/api/v1/*`) → 401 +
     `HX-Redirect: /auth/login`.
  2. API request (`/api/v1/...`) → 401 + NO HX-Redirect (consumers
     shouldn't auto-follow redirects to HTML pages).
  3. Non-HTMX UI request (no HX-Request header) → 401 + NO HX-Redirect
     (preserves the original behavior for curl / browser top-nav).
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
_UI_PATH = "/api/v1/discover/1/save"  # POST, gated, fragment response
_API_PATH = "/api/v1/profile/full_name"


def test_htmx_ui_request_401_emits_hx_redirect(client: TestClient):
    """No cookie + HX-Request header → 401 + HX-Redirect: /auth/login."""
    # `/api/v1/...` is API-prefixed so we need a non-API gated route. Use
    # one of the discover non-API endpoints; the cleanest path is the
    # `/discover` page itself (GET, no cookie → 401).
    r = client.get(
        "/discover",
        headers={"HX-Request": "true"},
        cookies={},
        follow_redirects=False,
    )
    # `/discover` uses `require_authed_session`; missing cookie → 401.
    assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text[:200]}"
    assert r.headers.get("hx-redirect") == "/auth/login"


def test_api_request_401_no_hx_redirect(client: TestClient):
    """`/api/v1/...` 401 stays bare — no HX-Redirect header."""
    r = client.put(
        _API_PATH,
        cookies={},
        data={"value": "New"},
    )
    assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text[:200]}"
    # Header is either absent OR empty; both acceptable, but the bug-fix
    # contract is "no auto-redirect" — pin "header not present".
    assert r.headers.get("hx-redirect") is None


def test_non_htmx_ui_request_401_no_hx_redirect(client: TestClient):
    """Plain HTTP UI request (no HX-Request header) → bare 401."""
    r = client.get("/discover", cookies={}, follow_redirects=False)
    assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text[:200]}"
    assert r.headers.get("hx-redirect") is None


def test_htmx_api_request_401_no_hx_redirect(client: TestClient):
    """HTMX request hitting `/api/v1/*` → bare 401 (API path wins over HTMX hint)."""
    r = client.put(
        _API_PATH,
        cookies={},
        data={"value": "New"},
        headers={"HX-Request": "true"},
    )
    assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text[:200]}"
    assert r.headers.get("hx-redirect") is None
