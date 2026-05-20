"""JWT revocation denylist tests — plan 50 § D.6 (0.2.1.04).

Six in-memory sqlite tests cover the `RevokedJwt` lifecycle:

1. `issue_jwt` carries a non-empty `jti` claim.
2. `revoke_jwt` inserts a row.
3. `is_jwt_revoked` returns True after revoke.
4. `is_jwt_revoked` returns False for unknown jti.
5. Authed `GET /api/v1/auth/me` returns 401 after the issued JWT is revoked.
6. `cleanup_expired_revoked_jwts` deletes only rows whose `expires_at`
   has passed; surviving rows stay intact.

All tests run against `sqlite+aiosqlite:///:memory:` so the suite stays
sub-second + DB-independent.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

# Bcrypt cost low for any password handling that side-effects through these tests.
os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")
os.environ.setdefault("NAAVIK_DEBUG", "1")

import jwt as pyjwt
import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from config import settings as app_settings
from models import RevokedJwt, User
from services.auth import (
    JWT_ALGORITHM,
    cleanup_expired_revoked_jwts,
    is_jwt_revoked,
    issue_jwt,
    revoke_jwt,
    verify_jwt,
)


@pytest.fixture
async def _session():
    """Per-test sqlite engine + session.

    Only `user` + `revoked_jwt` are created; the full `SQLModel.metadata`
    contains Postgres ARRAY columns (`JobScrapeRun.errors`) that sqlite
    cannot compile.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: SQLModel.metadata.create_all(
                sync_conn,
                tables=[User.__table__, RevokedJwt.__table__],
            )
        )
    sm = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sm() as session:
        yield session
    await engine.dispose()


async def _seed_user(session) -> User:
    user = User(
        id=1,
        email="dev@local",
        password_hash="$2b$04$placeholder.hash.for.test.only",
        is_active=True,
        is_admin=True,
        must_change_password=False,
    )
    session.add(user)
    await session.commit()
    return user


# ── 1 — issue_jwt carries jti ────────────────────────────────────────────


def test_jwt_carries_jti_claim() -> None:
    token = issue_jwt(user_id=42)
    payload = pyjwt.decode(token, app_settings.secret_key, algorithms=[JWT_ALGORITHM])
    assert "jti" in payload
    assert isinstance(payload["jti"], str)
    assert len(payload["jti"]) >= 22  # secrets.token_urlsafe(16) → 22 chars


# ── 2 — revoke_jwt inserts row ───────────────────────────────────────────


async def test_revoke_jwt_inserts_row(_session) -> None:
    await _seed_user(_session)
    expires = datetime.now(UTC) + timedelta(hours=1)
    await revoke_jwt(_session, jti="jti-1", user_id=1, expires_at=expires)
    await _session.commit()

    rows = (await _session.exec(select(RevokedJwt))).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.jti == "jti-1"
    assert row.user_id == 1
    # SQLite drops tzinfo on round-trip; compare naively after stripping.
    assert row.expires_at.replace(tzinfo=None) == expires.replace(tzinfo=None)


# ── 3 — is_jwt_revoked returns True after revoke ─────────────────────────


async def test_is_jwt_revoked_true_after_revoke(_session) -> None:
    await _seed_user(_session)
    await revoke_jwt(
        _session,
        jti="jti-2",
        user_id=1,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    await _session.commit()

    assert await is_jwt_revoked(_session, jti="jti-2") is True


# ── 4 — is_jwt_revoked returns False for unknown jti ─────────────────────


async def test_is_jwt_revoked_false_for_unknown(_session) -> None:
    await _seed_user(_session)
    assert await is_jwt_revoked(_session, jti="never-revoked") is False


# ── 5 — authed request rejected after revoke ─────────────────────────────


async def test_authed_request_rejected_after_revoke(_session) -> None:
    """End-to-end: issue JWT → set cookie → call /api/v1/auth/me OK → revoke
    the jti → call again → 401.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.auth import router as api_auth_router
    from db.session import get_session

    user = await _seed_user(_session)

    app = FastAPI()
    app.include_router(api_auth_router)

    async def _override_session():
        yield _session

    app.dependency_overrides[get_session] = _override_session
    client = TestClient(app)

    token = issue_jwt(user_id=user.id)
    result = verify_jwt(token)
    assert result is not None
    _, jti, exp = result

    # Pre-revoke: /me returns 200.
    r = client.get("/api/v1/auth/me", cookies={"naavik_session": token})
    assert r.status_code == 200, r.text

    # Revoke.
    await revoke_jwt(_session, jti=jti, user_id=user.id, expires_at=exp)
    await _session.commit()

    # Post-revoke: 401 + "revoked" in detail.
    r = client.get("/api/v1/auth/me", cookies={"naavik_session": token})
    assert r.status_code == 401
    assert "revoked" in r.text.lower()


# ── 6 — cleanup prunes expired rows ──────────────────────────────────────


async def test_cleanup_prunes_expired_rows(_session) -> None:
    await _seed_user(_session)
    past = datetime.now(UTC) - timedelta(hours=1)
    future = datetime.now(UTC) + timedelta(hours=1)
    await revoke_jwt(_session, jti="jti-expired", user_id=1, expires_at=past)
    await revoke_jwt(_session, jti="jti-future", user_id=1, expires_at=future)
    await _session.commit()

    n = await cleanup_expired_revoked_jwts(_session)
    await _session.commit()
    assert n == 1

    rows = (await _session.exec(select(RevokedJwt))).all()
    assert len(rows) == 1
    assert rows[0].jti == "jti-future"


# ── Bonus — multi-user isolation ─────────────────────────────────────────


async def test_change_password_revokes_old_jwt_end_to_end(_session) -> None:
    """End-to-end: POST /api/v1/auth/change-password → old JWT cookie 401s
    on the next /api/v1/auth/me hit. Proof that the operator-visible
    "rotate password locks out the prior session" intuition holds.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.auth import router as api_auth_router
    from db.session import get_session
    from services.auth import hash_password, issue_csrf_token

    # Seed a user with a known bcrypt hash so verify_password works.
    plain = "OriginalPass123"
    user = User(
        id=1,
        email="dev@local",
        password_hash=hash_password(plain),
        is_active=True,
        is_admin=True,
        must_change_password=False,
    )
    _session.add(user)
    await _session.commit()

    app = FastAPI()
    app.include_router(api_auth_router)

    async def _override_session():
        yield _session

    app.dependency_overrides[get_session] = _override_session
    client = TestClient(app)

    old_token = issue_jwt(user_id=user.id)
    csrf = issue_csrf_token()

    # Pre-rotation: /me works.
    r = client.get("/api/v1/auth/me", cookies={"naavik_session": old_token})
    assert r.status_code == 200

    # Rotate.
    r = client.post(
        "/api/v1/auth/change-password",
        data={"current_password": plain, "new_password": "BrandNewPass123"},
        cookies={"naavik_session": old_token, "naavik_csrf": csrf},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 204, r.text

    # Post-rotation: old JWT is rejected.
    r2 = client.get("/api/v1/auth/me", cookies={"naavik_session": old_token})
    assert r2.status_code == 401
    assert "revoked" in r2.text.lower()

    # NEW JWT (from the rotation Set-Cookie) works.
    new_token = r.cookies.get("naavik_session")
    assert new_token and new_token != old_token
    r3 = client.get("/api/v1/auth/me", cookies={"naavik_session": new_token})
    assert r3.status_code == 200


async def test_revocation_does_not_cross_users(_session) -> None:
    """Revoking user 1's jti must not affect user 2's tokens.

    Plan 50 prompt deliverable: "multi-user isolation". Two users +
    distinct jtis; revoke one, assert the other is untouched.
    """
    user1 = User(
        id=1,
        email="a@local",
        password_hash="$2b$04$placeholder.hash.for.test.only.aaa",
        is_active=True,
    )
    user2 = User(
        id=2,
        email="b@local",
        password_hash="$2b$04$placeholder.hash.for.test.only.bbb",
        is_active=True,
    )
    _session.add(user1)
    _session.add(user2)
    await _session.commit()

    exp = datetime.now(UTC) + timedelta(hours=1)
    await revoke_jwt(_session, jti="jti-user1", user_id=1, expires_at=exp)
    await _session.commit()

    assert await is_jwt_revoked(_session, jti="jti-user1") is True
    assert await is_jwt_revoked(_session, jti="jti-user2") is False
