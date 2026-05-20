"""Plan 45 (0.2.0.11d) — `csrf_token` Jinja context-processor.

Three regression tests for the cross-cutting defect surfaced at PR #138's
Manual QA gate: rendered HTML must carry the cookie's CSRF value in
`base.html`'s `hx-headers` JSON attribute + the `<meta name="csrf-token">`
tag — not the empty-string `| default('')` fallback that the production
HTMX flow hit pre-fix.

Both happy-path tests render through TestClient with a `naavik_csrf` cookie
set; the goal is to prove the context-processor reads the cookie + writes
it to the template ctx. The third locks in the empty-fallback invariant
that keeps `validate_csrf`'s empty-rejects-empty contract intact for
unauthenticated landing pages.
"""

from __future__ import annotations

import os

os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")


def test_discover_page_renders_csrf_token_from_cookie() -> None:
    """Rendering `/discover` with `naavik_csrf=<tok>` cookie surfaces
    `<tok>` in `base.html`'s `hx-headers` JSON + `<meta>` tag.

    Pre-fix behavior was `X-CSRF-Token: ""` regardless of cookie presence.
    Post-fix interpolates the cookie value.
    """
    from fastapi.testclient import TestClient

    from main import app
    from services.auth import require_authed_session

    async def _bypass_auth():
        return None

    app.dependency_overrides[require_authed_session] = _bypass_auth
    try:
        client = TestClient(app, raise_server_exceptions=True)
        tok = "test-csrf-token-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        r = client.get("/discover", cookies={"naavik_csrf": tok})
    finally:
        app.dependency_overrides.pop(require_authed_session, None)

    assert r.status_code == 200
    assert f'"X-CSRF-Token": "{tok}"' in r.text
    assert f'name="csrf-token" content="{tok}"' in r.text


def test_change_password_page_renders_csrf_token_from_cookie() -> None:
    """Rendering `/auth/change-password` with `naavik_csrf` cookie threads
    the value into the page so the HTMX form-POST carries
    `X-CSRF-Token: <tok>` instead of `""` (latent since plan 18).
    """
    from fastapi.testclient import TestClient

    from main import app
    from models import User
    from services.auth import get_current_user

    def _fake_user() -> User:
        return User(
            id=1,
            email="dev@local",
            password_hash="$2b$04$placeholder.hash.for.test.only",
            is_active=True,
            is_admin=True,
            must_change_password=True,
        )

    app.dependency_overrides[get_current_user] = _fake_user
    try:
        client = TestClient(app, raise_server_exceptions=True)
        tok = "test-csrf-token-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        r = client.get("/auth/change-password", cookies={"naavik_csrf": tok})
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert r.status_code == 200
    assert f'"X-CSRF-Token": "{tok}"' in r.text
    assert f'name="csrf-token" content="{tok}"' in r.text


def test_discover_page_empty_csrf_token_when_cookie_absent() -> None:
    """Absent `naavik_csrf` cookie → rendered `csrf_token` is `""`
    (preserves the `validate_csrf` empty-rejects-empty invariant).

    Guards against accidental misconfig (e.g. processor minting a fresh
    `issue_csrf_token()` per render would break the double-submit
    cookie/header pairing).
    """
    from fastapi.testclient import TestClient

    from main import app
    from services.auth import require_authed_session

    async def _bypass_auth():
        return None

    app.dependency_overrides[require_authed_session] = _bypass_auth
    try:
        client = TestClient(app, raise_server_exceptions=True)
        r = client.get("/discover")
    finally:
        app.dependency_overrides.pop(require_authed_session, None)

    assert r.status_code == 200
    assert '"X-CSRF-Token": ""' in r.text
