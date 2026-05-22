"""Plan 23 (PC.6a, 2026-05-18) — `require_authed_session` per-route-group tests.

The wrapper at `src/services/auth.py:require_authed_session` gates state-
changing UI + API routes whose substrate is the plan-09 fake-session cookie.
This file exercises one mutation route per gated group to confirm:

  1. Fake-session callers (cookie `naavik_session=fake-1`) pass through the
     gate (the wrapper returns None) — proves the 15 existing fake-session
     test files won't regress.
  2. Unauthenticated callers (no cookie) get 401 from every gated route.
  3. Real-JWT callers carrying a flagged user (must_change_password=True)
     get 403 from /api/v1/* routes and 307 from non-/api/v1/* routes, with
     `HX-Redirect: /auth/change-password` on both branches.

Routes covered (1 per group):
  - src/api/profile.py        → PUT /api/v1/profile/{field}
  - src/api/settings.py       → PUT /api/v1/settings/auto-apply
  - src/ui/routes/discover.py → POST /api/v1/discover/{id}/save
  - src/ui/routes/outreach.py → POST /api/v1/contacts
  - src/ui/routes/settings.py → PUT /api/v1/settings/notifications

Plus cross-cutting:
  - test_unauthenticated_caller_gets_401 (no-cookie sweep)
  - test_fake_session_caller_unaffected (fake-1 sweep across all 5 groups)
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.uses_sample_data_shims

# Tests bcrypt-init: keep cost low (same as test_auth.py).
os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")


@pytest.fixture(scope="module")
def client() -> TestClient:
    from main import app

    return TestClient(app)


def _flagged_user():
    """A User row flagged must_change_password=True. Used as the override
    for `get_user_by_id` so the wrapper's flag-check branch fires.
    """
    from models import User

    return User(
        id=1,
        email="dev@local",
        password_hash="$2b$04$placeholder.hash.for.test.only",
        is_active=True,
        is_admin=True,
        must_change_password=True,
    )


def _unflagged_user():
    from models import User

    return User(
        id=1,
        email="dev@local",
        password_hash="$2b$04$placeholder.hash.for.test.only",
        is_active=True,
        is_admin=True,
        must_change_password=False,
    )


_FAKE_JWT_RESULT = (1, "fake-jti-test-aaaaaaaaaaaaaaaaaaaaa", None)


def _async_false(*_a, **_kw):
    async def _inner(*_aa, **_kk):
        return False

    return _inner()


@pytest.fixture
def flag_real_jwt(monkeypatch):
    """Monkey-patch `verify_jwt` to accept any cookie + `get_user_by_id` to
    return a flagged user. The wrapper's fake-session check sees a non-
    `fake-1` cookie, falls into the real-JWT branch, decodes to user_id=1,
    looks up the flagged user, raises 307/403.

    Plan 50 (0.2.1.04): `verify_jwt` now returns
    `tuple[int, str, datetime] | None` so the lambda yields the tuple
    shape; `is_jwt_revoked` is patched to always-False so the wrapper's
    new denylist check doesn't fire.
    """
    from datetime import UTC, datetime, timedelta

    from services import auth as auth_svc

    fake_exp = datetime.now(UTC) + timedelta(hours=1)
    fake_result = (1, "fake-jti-test-aaaaaaaaaaaaaaaaaaaaa", fake_exp)

    async def fake_verify_jwt_async(session, token: str, *, tenant_id=1):
        if token == "fake-1":
            return None
        return fake_result

    async def fake_get_user_by_id(session, user_id: int):
        return _flagged_user()

    async def fake_is_jwt_revoked(session, *, jti: str) -> bool:
        return False

    monkeypatch.setattr(auth_svc, "verify_jwt_async", fake_verify_jwt_async)
    monkeypatch.setattr(auth_svc, "get_user_by_id", fake_get_user_by_id)
    monkeypatch.setattr(auth_svc, "is_jwt_revoked", fake_is_jwt_revoked)


@pytest.fixture
def real_jwt_unflagged(monkeypatch):
    """Same as `flag_real_jwt` but returns an unflagged user — gate passes."""
    from datetime import UTC, datetime, timedelta

    from services import auth as auth_svc

    fake_exp = datetime.now(UTC) + timedelta(hours=1)
    fake_result = (1, "fake-jti-test-aaaaaaaaaaaaaaaaaaaaa", fake_exp)

    async def fake_verify_jwt_async(session, token: str, *, tenant_id=1):
        if token == "fake-1":
            return None
        return fake_result

    async def fake_get_user_by_id(session, user_id: int):
        return _unflagged_user()

    async def fake_is_jwt_revoked(session, *, jti: str) -> bool:
        return False

    monkeypatch.setattr(auth_svc, "verify_jwt_async", fake_verify_jwt_async)
    monkeypatch.setattr(auth_svc, "get_user_by_id", fake_get_user_by_id)
    monkeypatch.setattr(auth_svc, "is_jwt_revoked", fake_is_jwt_revoked)


# ── Group 1 — api/profile mutations ─────────────────────────────────────


def test_api_profile_put_403_when_flagged(client: TestClient, flag_real_jwt):
    """PUT /api/v1/profile/full_name with a flagged-user JWT → 403 + HX-Redirect."""
    r = client.put(
        "/api/v1/profile/full_name",
        cookies={"naavik_session": "fake-jwt-token"},
        data={"value": "New Name"},
    )
    assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"
    assert r.headers.get("hx-redirect") == "/auth/change-password"


# ── Group 2 — api/settings mutations ─────────────────────────────────────


def test_api_settings_put_403_when_flagged(client: TestClient, flag_real_jwt):
    """PUT /api/v1/settings/auto-apply with a flagged-user JWT → 403."""
    r = client.put(
        "/api/v1/settings/auto-apply",
        cookies={"naavik_session": "fake-jwt-token"},
        json={"auto_apply_enabled": True},
    )
    assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"
    assert r.headers.get("hx-redirect") == "/auth/change-password"


# ── Group 3 — ui/routes/discover mutations ───────────────────────────────


def test_ui_route_discover_save_403_when_flagged(client: TestClient, flag_real_jwt):
    """POST /api/v1/discover/{id}/save with a flagged-user JWT → 403.

    Plan 44 (0.2.0.11b) added `Depends(require_csrf)` to this endpoint;
    matching CSRF pair threaded through so the auth-gate is the only
    remaining gate (not short-circuited by CSRF 403).
    """
    csrf = "matching-csrf-flagged-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    r = client.post(
        "/api/v1/discover/1/save",
        cookies={"naavik_session": "fake-jwt-token", "naavik_csrf": csrf},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"
    assert r.headers.get("hx-redirect") == "/auth/change-password"


# ── Group 4 — ui/routes/outreach mutations ───────────────────────────────


def test_ui_route_outreach_contacts_post_403_when_flagged(client: TestClient, flag_real_jwt):
    """POST /api/v1/contacts with a flagged-user JWT → 403."""
    r = client.post(
        "/api/v1/contacts",
        cookies={"naavik_session": "fake-jwt-token"},
        json={"name": "Test"},
    )
    assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"
    assert r.headers.get("hx-redirect") == "/auth/change-password"


# ── Group 5 — ui/routes/settings mutations ───────────────────────────────


def test_ui_route_settings_put_403_when_flagged(client: TestClient, flag_real_jwt):
    """PUT /api/v1/settings/notifications with a flagged-user JWT → 403."""
    r = client.put(
        "/api/v1/settings/notifications",
        cookies={"naavik_session": "fake-jwt-token"},
        json={"notifications_enabled": True},
    )
    assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"
    assert r.headers.get("hx-redirect") == "/auth/change-password"


# ── Cross-cutting — fake-session must not regress ────────────────────────


def test_fake_session_caller_unaffected_across_groups(client: TestClient):
    """The 15 existing fake-session test files use cookie naavik_session=fake-1.
    The new wrapper must return None for them so the route bodies run
    unchanged. We check one route per group + assert the gate did NOT fire
    (no 303/307/401/403 from the wrapper). The route's own logic may return
    other codes (200/204/422/400/404) — those are fine, just not the gate
    codes.

    Routes picked here MUST be ones whose handler bodies don't touch the
    live DB (sample_data accessors only) — otherwise the test couples to
    NAAVIK_LIVE_DB. The fake-session gate behavior is what's under test;
    DB-touching routes have their own per-file fake-session coverage.
    """
    gate_codes = {303, 307, 401, 403}

    # ui/routes/discover — in-memory sample_data. Plan 44 (0.2.0.11b) added
    # `Depends(require_csrf)` to discover_save; matching CSRF pair threaded
    # so the gate-under-test (fake-session pass-through) isn't masked by
    # a CSRF 403.
    csrf = "matching-csrf-fake-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    r = client.post(
        "/api/v1/discover/1/save",
        cookies={"naavik_session": "fake-1", "naavik_csrf": csrf},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code not in gate_codes, f"ui/discover gate misfired on fake-1: {r.status_code}"

    # ui/routes/outreach — in-memory sample_data
    r = client.post(
        "/api/v1/contacts",
        cookies={"naavik_session": "fake-1"},
        json={"name": "Test"},
    )
    assert r.status_code not in gate_codes, f"ui/outreach gate misfired on fake-1: {r.status_code}"

    # ui/routes/settings — DB-free fragment route (POST renders a card)
    r = client.post(
        "/_fragments/settings/test-connection?provider=anthropic",
        cookies={"naavik_session": "fake-1"},
    )
    assert r.status_code not in gate_codes, f"ui/settings gate misfired on fake-1: {r.status_code}"
    # Plan 42 LOW Note 2 fold-in: pin one representative positive-route
    # response so a future change that turns this route into a 500 doesn't
    # silently pass the negative-only sweep above.
    assert r.status_code in {200, 204, 422}, (
        f"ui/settings test-connection should return 200/204/422; got {r.status_code}"
    )

    # ui/routes/email — read sample_data thread, no DB write
    r = client.post(
        "/api/v1/email/threads/1/draft-reply",
        cookies={"naavik_session": "fake-1"},
        json={"intent": "follow_up"},
    )
    assert r.status_code not in gate_codes, f"ui/email gate misfired on fake-1: {r.status_code}"

    # ui/routes/integrations — in-memory _INTEGRATIONS dict
    r = client.post(
        "/api/v1/integrations/outlook/disconnect",
        cookies={"naavik_session": "fake-1"},
    )
    assert r.status_code not in gate_codes, (
        f"ui/integrations gate misfired on fake-1: {r.status_code}"
    )


# ── Cross-cutting — no cookie → 401 ──────────────────────────────────────


def test_unauthenticated_caller_gets_401_across_groups(client: TestClient):
    """No `naavik_session` cookie at all → 401 from every gated route.

    The gate fires BEFORE the route body, so DB-touching routes are safe
    to include here — the 401 short-circuits any DB query.
    """
    r = client.put(
        "/api/v1/profile/full_name",
        data={"value": "Test"},
    )
    assert r.status_code == 401, f"api/profile expected 401, got {r.status_code}"

    r = client.put(
        "/api/v1/settings/auto-apply",
        json={"auto_apply_enabled": True},
    )
    assert r.status_code == 401, f"api/settings expected 401, got {r.status_code}"

    r = client.post("/api/v1/discover/1/save")
    assert r.status_code == 401, f"ui/discover expected 401, got {r.status_code}"

    r = client.post("/api/v1/contacts", json={"name": "Test"})
    assert r.status_code == 401, f"ui/outreach expected 401, got {r.status_code}"

    r = client.put("/api/v1/settings/notifications", json={"notifications_enabled": True})
    assert r.status_code == 401, f"ui/settings expected 401, got {r.status_code}"


# ── Plan 42 (0.2.0.04 / PC.6b) — onboarding-bypass precondition ──────────


class _FakeUserCountSession:
    """Stand-in `AsyncSession` whose `.exec(...)` returns a result wrapping
    the configured count value. Mirrors the shape `_compute_signup_disabled`
    + `post_signup` unwrap (`.one()` returns a tuple-like with `[0]` = int).
    """

    def __init__(self, count: int) -> None:
        self._count = count

    async def exec(self, _stmt):
        count = self._count

        class _Result:
            def one(self):
                return (count,)

        return _Result()


def _override_session_with_count(count: int):
    from db.session import get_session
    from main import app

    async def _fake_get_session():
        yield _FakeUserCountSession(count)

    app.dependency_overrides[get_session] = _fake_get_session
    return get_session


def test_from_extraction_blocked_when_user_exists(client: TestClient):
    """Existing User row → 409 + 'Account already exists' card + cookie NOT set."""
    dep = _override_session_with_count(1)
    try:
        r = client.post("/api/v1/profile/from-extraction")
    finally:
        from main import app

        app.dependency_overrides.pop(dep, None)
    assert r.status_code == 409, f"expected 409, got {r.status_code}: {r.text}"
    assert "Account already exists" in r.text
    assert "naavik_session" not in {c.name for c in r.cookies.jar}


def test_from_extraction_blocked_when_flagged_user_exists(client: TestClient):
    """Hacker MEDIUM probe path — flagged user already exists, attacker POSTs
    to `from-extraction` hoping to replace real-JWT with fake-session. Count
    probe sees the row and returns 409 without writing the cookie.
    """
    dep = _override_session_with_count(1)
    try:
        r = client.post("/api/v1/profile/from-extraction")
    finally:
        from main import app

        app.dependency_overrides.pop(dep, None)
    assert r.status_code == 409, f"expected 409, got {r.status_code}: {r.text}"
    assert "naavik_session" not in {c.name for c in r.cookies.jar}


def test_from_extraction_allowed_on_fresh_db(client: TestClient):
    """Empty `User` table → 204 + `HX-Redirect: /` + `naavik_session=fake-1` cookie."""
    dep = _override_session_with_count(0)
    try:
        r = client.post("/api/v1/profile/from-extraction")
    finally:
        from main import app

        app.dependency_overrides.pop(dep, None)
    assert r.status_code == 204, f"expected 204, got {r.status_code}: {r.text}"
    assert r.headers.get("hx-redirect") == "/"
    assert r.cookies.get("naavik_session") == "fake-1"


def test_from_extraction_409_response_is_htmx_swappable(client: TestClient):
    """409 body is a bare HTML fragment (no `<html>`/`<body>` wrapping) so
    HTMX can swap it directly into `#onboarding-step-content`.
    """
    dep = _override_session_with_count(1)
    try:
        r = client.post("/api/v1/profile/from-extraction")
    finally:
        from main import app

        app.dependency_overrides.pop(dep, None)
    assert r.status_code == 409
    body = r.text.lower()
    assert "<html" not in body, "fragment must not contain <html>"
    assert "<body" not in body, "fragment must not contain <body>"
    assert 'id="onboarding-step-content"' in r.text, "fragment must carry the swap-target id"
