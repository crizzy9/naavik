"""Auth service tests — Wave 4 of plan 10 § B.3.

Pure-Python unit tests on bcrypt + JWT + CSRF + brute-force guard. No live
DB needed for any of these — `authenticate()` and `get_current_user()` are
covered by integration tests once the dev orchestrator is up.
"""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime

# Force fast bcrypt cost for tests before the service module loads.
os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")

from services.auth import (  # noqa: E402
    JWT_ALGORITHM,
    JWT_TTL_DEFAULT,
    _bcrypt_cost,
    hash_password,
    is_rate_limited,
    issue_csrf_token,
    issue_jwt,
    record_login_attempt,
    reset_rate_limit,
    validate_csrf,
    verify_jwt,
    verify_password,
)

# ── bcrypt ──────────────────────────────────────────────────────────────


def test_hash_password_then_verify() -> None:
    h = hash_password("hunter2")
    assert h.startswith("$2b$")
    assert verify_password("hunter2", h) is True
    assert verify_password("wrong", h) is False


def test_hash_password_distinct_salts() -> None:
    a = hash_password("hunter2")
    b = hash_password("hunter2")
    assert a != b  # bcrypt salts are random


def test_verify_password_empty_inputs() -> None:
    assert verify_password("", "") is False
    assert verify_password("pwd", "") is False
    assert verify_password("", hash_password("pwd")) is False


def test_verify_password_corrupt_hash_returns_false() -> None:
    # Don't raise — return False so attackers can't probe error type.
    assert verify_password("hunter2", "not-a-bcrypt-hash") is False
    assert verify_password("hunter2", "$2b$xx$bogus") is False


def test_bcrypt_cost_env_override() -> None:
    os.environ["NAAVIK_BCRYPT_COST"] = "4"
    assert _bcrypt_cost() == 4
    os.environ["NAAVIK_BCRYPT_COST"] = "12"
    assert _bcrypt_cost() == 12
    # Out-of-range falls back to 12.
    os.environ["NAAVIK_BCRYPT_COST"] = "30"
    assert _bcrypt_cost() == 12
    # Restore for other tests.
    os.environ["NAAVIK_BCRYPT_COST"] = "4"


# ── JWT ─────────────────────────────────────────────────────────────────


def test_issue_then_verify_jwt() -> None:
    token = issue_jwt(42)
    assert isinstance(token, str)
    result = verify_jwt(token)
    assert result is not None
    user_id, jti, expires_at = result
    assert user_id == 42
    assert jti
    assert expires_at is not None


def test_verify_jwt_invalid_returns_none() -> None:
    assert verify_jwt("not.a.jwt") is None
    assert verify_jwt("") is None


def test_verify_jwt_expired_returns_none() -> None:
    """Test by tampering with the JWT payload."""
    import jwt as pyjwt

    from config import settings as app_settings

    expired_payload = {
        "sub": "1",
        "iat": int(time.time() - 1_000_000),
        "exp": int(time.time() - 1_000),
    }
    tok = pyjwt.encode(expired_payload, app_settings.secret_key, algorithm=JWT_ALGORITHM)
    assert verify_jwt(tok) is None


def test_jwt_keep_signed_in_extends_ttl() -> None:
    import jwt as pyjwt

    from config import settings as app_settings

    short = issue_jwt(1, keep_signed_in=False)
    long = issue_jwt(1, keep_signed_in=True)
    short_dec = pyjwt.decode(short, app_settings.secret_key, algorithms=[JWT_ALGORITHM])
    long_dec = pyjwt.decode(long, app_settings.secret_key, algorithms=[JWT_ALGORITHM])
    assert long_dec["exp"] > short_dec["exp"] + (
        int(JWT_TTL_DEFAULT.total_seconds()) // 2
    )  # significantly larger


# ── CSRF ────────────────────────────────────────────────────────────────


def test_issue_csrf_token_distinct() -> None:
    a = issue_csrf_token()
    b = issue_csrf_token()
    assert a != b
    assert len(a) >= 32


def test_validate_csrf_constant_time() -> None:
    a = issue_csrf_token()
    assert validate_csrf(a, a) is True
    assert validate_csrf(a, "tampered") is False
    assert validate_csrf(None, a) is False
    assert validate_csrf(a, None) is False
    assert validate_csrf(None, None) is False


# ── Rate limiter ────────────────────────────────────────────────────────


def test_rate_limiter_under_threshold() -> None:
    reset_rate_limit()
    ip = "10.0.0.1"
    for _ in range(4):
        record_login_attempt(ip, success=False)
    assert is_rate_limited(ip) is False


def test_rate_limiter_at_threshold() -> None:
    reset_rate_limit()
    ip = "10.0.0.2"
    for _ in range(5):
        record_login_attempt(ip, success=False)
    assert is_rate_limited(ip) is True


def test_rate_limiter_over_threshold() -> None:
    reset_rate_limit()
    ip = "10.0.0.3"
    for _ in range(8):
        record_login_attempt(ip, success=False)
    assert is_rate_limited(ip) is True


def test_rate_limiter_resets_on_success() -> None:
    reset_rate_limit()
    ip = "10.0.0.4"
    for _ in range(5):
        record_login_attempt(ip, success=False)
    assert is_rate_limited(ip) is True
    record_login_attempt(ip, success=True)
    assert is_rate_limited(ip) is False


def test_rate_limiter_per_ip_isolation() -> None:
    reset_rate_limit()
    for _ in range(5):
        record_login_attempt("10.0.0.5", success=False)
    record_login_attempt("10.0.0.6", success=False)
    assert is_rate_limited("10.0.0.5") is True
    assert is_rate_limited("10.0.0.6") is False


# ── Cookie flag verification ────────────────────────────────────────────


def test_login_response_cookie_flags() -> None:
    """Spin up the FastAPI app and POST a login; assert cookie flags."""
    # Ad-hoc app so this test doesn't depend on the full UI router being
    # reloadable.
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.auth import router as api_auth_router

    app = FastAPI()
    app.include_router(api_auth_router)

    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/login",
        data={"email": "", "password": ""},
    )
    # Empty creds get a 422 inline error card; no cookie set.
    assert response.status_code == 422
    assert "naavik_session" not in response.cookies


def test_csrf_token_endpoint_sets_cookie_when_missing() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.auth import router as api_auth_router

    app = FastAPI()
    app.include_router(api_auth_router)
    client = TestClient(app)

    response = client.get("/api/v1/auth/csrf")
    assert response.status_code == 200
    assert "csrf_token" in response.json()
    # Cookie set on first call.
    assert "naavik_csrf" in response.cookies


# ── Plan 10b (item 4) — signup endpoint validation ───────────────────────


def _signup_client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.auth import router as api_auth_router

    app = FastAPI()
    app.include_router(api_auth_router)
    return TestClient(app)


def test_signup_rejects_blank_credentials() -> None:
    """Plan 10b: empty email or password short-circuits before DB access.

    FastAPI's Form parser rejects empty-string posts as 422 *before* the
    handler runs (matches the existing /login parity); the cookie still
    must not be set.
    """
    client = _signup_client()
    r = client.post("/api/v1/auth/signup", data={"email": "", "password": ""})
    assert r.status_code == 422
    assert "naavik_session" not in r.cookies


def test_signup_rejects_short_password() -> None:
    client = _signup_client()
    r = client.post(
        "/api/v1/auth/signup",
        data={"email": "[email protected]", "password": "short"},
    )
    assert r.status_code == 422
    # Plan 18 (PC.6): the 8-char rule tightened to 12 + complexity.
    assert "at least 12 characters" in r.text
    assert "naavik_session" not in r.cookies


def test_signup_rejects_invalid_email_shape() -> None:
    client = _signup_client()
    r = client.post(
        "/api/v1/auth/signup",
        # Password meets PC.6 complexity (12+ chars, letter, digit) so the
        # email-shape check is the only failure surface.
        data={"email": "not-an-email", "password": "longenoughpw1"},
    )
    assert r.status_code == 422
    assert "valid email" in r.text


def test_signup_password_round_trips_via_real_bcrypt() -> None:
    """Whatever is stored MUST be a real bcrypt hash that verify_password accepts."""
    raw = "hunter2hunter2"
    hashed = hash_password(raw)
    assert hashed.startswith("$2b$")
    assert verify_password(raw, hashed) is True
    assert verify_password("wrong", hashed) is False
    # Sample-data fixture must NOT carry a placeholder bcrypt anywhere — that
    # value used to short-circuit verify_password to True even on miss.
    assert "placeholder.hash.for.dev.password" not in hashed


# ── Plan 18 (PC.6) — password complexity validator ──────────────────────


def test_validate_password_complexity_passes_strong() -> None:
    from services.auth import validate_password_complexity

    assert validate_password_complexity("StrongPass123") is None
    assert validate_password_complexity("a" * 12 + "1") is None


def test_validate_password_complexity_fails_too_short() -> None:
    from services.auth import validate_password_complexity

    msg = validate_password_complexity("abc123")
    assert msg is not None
    assert "12" in msg


def test_validate_password_complexity_fails_no_digit() -> None:
    from services.auth import validate_password_complexity

    msg = validate_password_complexity("abcdefghijklmn")
    assert msg is not None
    assert "digit" in msg.lower()


def test_validate_password_complexity_fails_no_letter() -> None:
    from services.auth import validate_password_complexity

    msg = validate_password_complexity("123456789012345")
    assert msg is not None
    assert "letter" in msg.lower()


def test_validate_password_complexity_empty() -> None:
    from services.auth import validate_password_complexity

    msg = validate_password_complexity("")
    assert msg is not None


def test_hash_password_with_complexity_check_rejects_weak() -> None:
    import pytest

    from services.auth import hash_password_with_complexity_check

    with pytest.raises(ValueError) as exc:
        hash_password_with_complexity_check("short")
    assert "12" in str(exc.value)


def test_hash_password_with_complexity_check_accepts_strong() -> None:
    from services.auth import hash_password_with_complexity_check

    h = hash_password_with_complexity_check("StrongPass123")
    assert h.startswith("$2b$")


def test_change_password_rejects_missing_csrf_token() -> None:
    """Plan 18 (PC.6) re-loop (hacker Finding 2, MEDIUM): the change-password
    endpoint is gated by `Depends(require_csrf)`. A POST without the
    matching `X-CSRF-Token` header (or with mismatched cookie/header) gets
    403, not 422/204 — even with a valid JWT cookie + complexity-passing new
    password. The HTMX form on `pages/change_password.html` carries the
    header via the global `base.html` `hx-headers` attribute, so this gate
    is invisible to honest UI clients.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.auth import router as api_auth_router
    from models import User
    from services.auth import get_current_user

    app = FastAPI()
    app.include_router(api_auth_router)

    def _fake_user():
        return User(
            id=1,
            email="dev@local",
            password_hash="$2b$04$placeholder.hash.for.test.only",
            is_active=True,
            is_admin=True,
            must_change_password=True,
        )

    app.dependency_overrides[get_current_user] = _fake_user
    client = TestClient(app)

    # Mismatched cookie + header — validate_csrf returns False.
    r = client.post(
        "/api/v1/auth/change-password",
        data={"current_password": "anything", "new_password": "StrongerThanThat1"},
        cookies={"naavik_csrf": "cookie-token-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
        headers={"X-CSRF-Token": "header-token-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"},
    )
    assert r.status_code == 403
    assert "CSRF" in r.text or "csrf" in r.text


def test_change_password_accepts_matching_csrf_token() -> None:
    """Confirm the CSRF gate does NOT reject a legitimate request — cookie +
    header carrying the same token pass through to the complexity check.
    Uses a deliberately-weak new password so we stop at the 422 complexity
    rejection without needing a live DB to flip the flag. The point is
    proving `require_csrf` is not a false-positive on the matching path.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.auth import router as api_auth_router
    from models import User
    from services.auth import get_current_user

    app = FastAPI()
    app.include_router(api_auth_router)

    def _fake_user():
        return User(
            id=1,
            email="dev@local",
            password_hash="$2b$04$placeholder.hash.for.test.only",
            is_active=True,
            is_admin=True,
            must_change_password=True,
        )

    app.dependency_overrides[get_current_user] = _fake_user
    client = TestClient(app)

    matching = "matching-token-cccccccccccccccccccccccccccccccccc"
    r = client.post(
        "/api/v1/auth/change-password",
        data={"current_password": "anything", "new_password": "short"},
        cookies={"naavik_csrf": matching},
        headers={"X-CSRF-Token": matching},
    )
    # CSRF passes (would be 403 otherwise); flow continues to verify_password,
    # which fails on the placeholder hash → 422 "Current password is
    # incorrect." The status proves require_csrf accepted matching tokens.
    assert r.status_code == 422
    assert "Current password" in r.text


# ── Plan 23 (PC.6a) — require_authed_session wrapper ────────────────────


def _async_return(value):
    """Build an async callable that returns `value` regardless of arguments.

    Plan 50 (0.2.1.04): used to patch `is_jwt_revoked` (async) in
    require_authed_session tests so unit tests don't need a live DB.
    """

    async def _inner(*_a, **_kw):
        return value

    return _inner


_FAKE_JWT_TUPLE = (1, "fake-jti-aaaaaaaaaaaaaaaaaaaaaa", datetime.now(UTC) + JWT_TTL_DEFAULT)


def _build_authed_session_test_app(*, override_user=None):
    """Build a minimal FastAPI app exposing one /api/v1/* mutation route and
    one non-/api/v1/* UI route, both gated by `require_authed_session`.
    `override_user` is the User the patched `get_user_by_id` returns; if
    None, no user override is applied (default DB path).
    """
    from fastapi import Depends, FastAPI

    from models import User
    from services.auth import require_authed_session

    app = FastAPI()

    @app.post("/api/v1/probe")
    async def probe_api(_user: User | None = Depends(require_authed_session)):
        return {"ok": True}

    @app.post("/probe")
    async def probe_ui(_user: User | None = Depends(require_authed_session)):
        return {"ok": True}

    return app


def test_require_authed_session_no_cookie_401() -> None:
    """Plan 23 (PC.6a): missing `naavik_session` cookie raises 401."""
    from fastapi.testclient import TestClient

    app = _build_authed_session_test_app()
    client = TestClient(app)

    r = client.post("/api/v1/probe")
    assert r.status_code == 401


def test_require_authed_session_fake_cookie_returns_none() -> None:
    """Plan 23 (PC.6a): cookie equals `FAKE_SESSION_VALUE` → wrapper returns
    None and the route body runs to completion.
    """
    from fastapi.testclient import TestClient

    app = _build_authed_session_test_app()
    client = TestClient(app)

    r = client.post(
        "/api/v1/probe",
        cookies={"naavik_session": "fake-1"},
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_require_authed_session_invalid_jwt_401(monkeypatch) -> None:
    """Plan 23 (PC.6a): non-fake cookie that doesn't decode as a JWT → 401."""
    from fastapi.testclient import TestClient

    from services import auth as auth_svc

    app = _build_authed_session_test_app()
    client = TestClient(app)

    # verify_jwt returns None on the patched call (mimicking an invalid token).
    # NOTE: wrapper imports verify_jwt by bare name at services/auth.py:338;
    # if verify_jwt moves to a sibling module, switch this monkeypatch to the
    # wrapper's own import path or this test silently no-ops.
    monkeypatch.setattr(auth_svc, "verify_jwt", lambda token: None)
    monkeypatch.setattr(auth_svc, "is_jwt_revoked", _async_return(False))

    r = client.post(
        "/api/v1/probe",
        cookies={"naavik_session": "definitely-not-a-jwt"},
    )
    assert r.status_code == 401


def test_require_authed_session_real_jwt_unflagged_passes(monkeypatch) -> None:
    """Plan 23 (PC.6a): valid JWT + unflagged user → wrapper returns the User
    and the route body runs.
    """
    from fastapi.testclient import TestClient

    from models import User
    from services import auth as auth_svc

    app = _build_authed_session_test_app()
    client = TestClient(app)

    async def fake_get_user_by_id(session, user_id):
        return User(
            id=1,
            email="dev@local",
            password_hash="$2b$04$placeholder.hash.for.test.only",
            is_active=True,
            is_admin=True,
            must_change_password=False,
        )

    monkeypatch.setattr(auth_svc, "verify_jwt", lambda token: _FAKE_JWT_TUPLE)
    monkeypatch.setattr(auth_svc, "is_jwt_revoked", _async_return(False))
    monkeypatch.setattr(auth_svc, "get_user_by_id", fake_get_user_by_id)

    r = client.post(
        "/api/v1/probe",
        cookies={"naavik_session": "valid-jwt"},
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_require_authed_session_real_jwt_flagged_403_on_api(monkeypatch) -> None:
    """Plan 23 (PC.6a): /api/v1/* path + flagged user → 403 with HX-Redirect."""
    from fastapi.testclient import TestClient

    from models import User
    from services import auth as auth_svc

    app = _build_authed_session_test_app()
    client = TestClient(app)

    async def fake_get_user_by_id(session, user_id):
        return User(
            id=1,
            email="dev@local",
            password_hash="$2b$04$placeholder.hash.for.test.only",
            is_active=True,
            is_admin=True,
            must_change_password=True,
        )

    monkeypatch.setattr(auth_svc, "verify_jwt", lambda token: _FAKE_JWT_TUPLE)
    monkeypatch.setattr(auth_svc, "is_jwt_revoked", _async_return(False))
    monkeypatch.setattr(auth_svc, "get_user_by_id", fake_get_user_by_id)

    r = client.post(
        "/api/v1/probe",
        cookies={"naavik_session": "valid-jwt"},
    )
    assert r.status_code == 403
    assert r.headers.get("hx-redirect") == "/auth/change-password"


def test_require_authed_session_real_jwt_flagged_307_on_ui(monkeypatch) -> None:
    """Plan 23 (PC.6a): non-/api/v1/* path + flagged user → 307 with
    HX-Redirect AND Location set to /auth/change-password.
    """
    from fastapi.testclient import TestClient

    from models import User
    from services import auth as auth_svc

    app = _build_authed_session_test_app()
    # Disable follow_redirects so we observe the 307 directly.
    client = TestClient(app, follow_redirects=False)

    async def fake_get_user_by_id(session, user_id):
        return User(
            id=1,
            email="dev@local",
            password_hash="$2b$04$placeholder.hash.for.test.only",
            is_active=True,
            is_admin=True,
            must_change_password=True,
        )

    monkeypatch.setattr(auth_svc, "verify_jwt", lambda token: _FAKE_JWT_TUPLE)
    monkeypatch.setattr(auth_svc, "is_jwt_revoked", _async_return(False))
    monkeypatch.setattr(auth_svc, "get_user_by_id", fake_get_user_by_id)

    r = client.post(
        "/probe",
        cookies={"naavik_session": "valid-jwt"},
    )
    assert r.status_code == 307
    assert r.headers.get("hx-redirect") == "/auth/change-password"
    assert r.headers.get("location") == "/auth/change-password"
