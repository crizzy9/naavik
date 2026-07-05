"""POST /api/v1/settings/security/rotate-jwt-key — plan 62 (0.2.7.07).

Covers:
- Missing CSRF → 403.
- Unauth → 401.
- Authed + CSRF → 200 + rotation persists.
- FUNC_REF_ALLOWLIST contains the new RETIRING sweep cron.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

os.environ.setdefault("NAAVIK_DEBUG", "1")
os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from api.auth import router as api_auth_router
from api.settings import router as api_settings_router
from db.session import get_session
from models import (
    RevokedJwt,
    Tenant,
    TenantSigningKey,
    TenantSigningKeyStatus,
    User,
)
from services.auth import issue_csrf_token, issue_jwt_async

pytestmark = pytest.mark.uses_sample_data_shims


@pytest.fixture
async def _session():
    """In-memory sqlite engine. The full Settings table has Postgres JSONB
    columns so we stand up a minimal Settings table inline (just the two
    columns the rotation flow reads) and skip the full SQLModel metadata.
    """
    import sqlalchemy as sa

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    def _create_tables(sync_conn):
        SQLModel.metadata.create_all(
            sync_conn,
            tables=[
                User.__table__,
                RevokedJwt.__table__,
                Tenant.__table__,
                TenantSigningKey.__table__,
            ],
        )
        meta = sa.MetaData()
        sa.Table(
            "settings",
            meta,
            sa.Column("user_id", sa.Integer, primary_key=True),
            sa.Column("jwt_rotation_days", sa.Integer, nullable=False, server_default="90"),
            sa.Column("jwt_rotation_grace_days", sa.Integer, nullable=False, server_default="7"),
        )
        meta.create_all(sync_conn)

    async with engine.begin() as conn:
        await conn.run_sync(_create_tables)
    sm = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sm() as session:
        session.add(Tenant(id=1, name="self-hosted"))
        session.add(
            User(
                id=1,
                email="dev@local",
                password_hash="$2b$04$placeholder.hash.for.test.only",
                is_active=True,
                is_admin=True,
                must_change_password=False,
            )
        )
        await session.exec(
            sa.text(
                "INSERT INTO settings (user_id, jwt_rotation_days, jwt_rotation_grace_days) "
                "VALUES (1, 90, 7)"
            )
        )
        await session.commit()
        yield session
    await engine.dispose()


def _build_app(session: AsyncSession) -> FastAPI:
    app = FastAPI()
    app.include_router(api_auth_router)
    app.include_router(api_settings_router)

    async def _override_session():
        yield session

    app.dependency_overrides[get_session] = _override_session
    return app


# ── Missing CSRF → 403 ────────────────────────────────────────────────────


async def test_rotate_jwt_key_missing_csrf_returns_403(_session) -> None:
    app = _build_app(_session)
    client = TestClient(app)

    token = await issue_jwt_async(_session, user_id=1, tenant_id=1)

    r = client.post(
        "/api/v1/settings/security/rotate-jwt-key",
        cookies={"naavik_session": token},
    )
    assert r.status_code == 403
    assert "CSRF" in r.text


# ── Missing auth → 401 ────────────────────────────────────────────────────


def test_rotate_jwt_key_no_cookie_returns_401(_session) -> None:
    app = _build_app(_session)
    client = TestClient(app)

    csrf = issue_csrf_token()
    r = client.post(
        "/api/v1/settings/security/rotate-jwt-key",
        cookies={"naavik_csrf": csrf},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 401


# ── Authed + CSRF → 200 + rotation persists ──────────────────────────────


async def test_rotate_jwt_key_authed_succeeds_and_persists(_session) -> None:
    app = _build_app(_session)
    client = TestClient(app)

    # Seed an initial ACTIVE key via direct insert (simulates post-migration state).
    from services.auth.jwt_rotation import rotate_tenant_key

    await rotate_tenant_key(_session, tenant_id=1)
    await _session.commit()
    pre_active = (
        await _session.exec(
            select(TenantSigningKey).where(
                TenantSigningKey.tenant_id == 1,
                TenantSigningKey.status == TenantSigningKeyStatus.ACTIVE,
            )
        )
    ).one()

    token = await issue_jwt_async(_session, user_id=1, tenant_id=1)
    csrf = issue_csrf_token()

    r = client.post(
        "/api/v1/settings/security/rotate-jwt-key",
        cookies={"naavik_session": token, "naavik_csrf": csrf},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, r.text
    # Returns the re-rendered Settings · Security card HTML.
    assert "JWT signing key" in r.text or "ACTIVE" in r.text or "kid" in r.text.lower()

    # DB state: old key now RETIRING, new key ACTIVE.
    await _session.refresh(pre_active)
    assert pre_active.status == TenantSigningKeyStatus.RETIRING
    actives = (
        await _session.exec(
            select(TenantSigningKey).where(TenantSigningKey.status == TenantSigningKeyStatus.ACTIVE)
        )
    ).all()
    assert len(actives) == 1
    assert actives[0].id != pre_active.id


# ── Concurrent rotation race → HTTP 409 ──────────────────────────────────


async def test_rotate_jwt_key_returns_409_on_integrity_error(_session, monkeypatch) -> None:
    """Concurrent-rotation race triggers IntegrityError → endpoint returns 409.

    We monkeypatch `rotate_tenant_key` to raise IntegrityError directly
    rather than reproducing the alembic 0015 partial unique index in
    the in-memory test schema (which is intentionally minimal — see the
    _session fixture's hand-built Settings table).
    """
    from sqlalchemy.exc import IntegrityError

    app = _build_app(_session)
    client = TestClient(app)

    token = await issue_jwt_async(_session, user_id=1, tenant_id=1)
    csrf = issue_csrf_token()

    import services.auth.jwt_rotation as svc

    async def _boom(*_args, **_kwargs):
        raise IntegrityError("conflict", params=None, orig=Exception("uq violation"))

    monkeypatch.setattr(svc, "rotate_tenant_key", _boom)

    r = client.post(
        "/api/v1/settings/security/rotate-jwt-key",
        cookies={"naavik_session": token, "naavik_csrf": csrf},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 409
    body = r.json()
    assert "rotation" in body["detail"].lower()


# ── Allowlist parity ──────────────────────────────────────────────────────


def test_func_ref_allowlist_contains_retiring_sweep() -> None:
    from scheduler.json_jobstore import FUNC_REF_ALLOWLIST

    assert "scheduler.jobs:expire_retiring_signing_keys" in FUNC_REF_ALLOWLIST


# ── Scheduler job body smoke (drives the sweep) ───────────────────────────


async def test_expire_retiring_cron_body_smokes(_session) -> None:
    """Smoke test the cron body's DB I/O against an in-memory session.

    We patch `async_session` to yield our test session so the cron's
    `async with async_session() as session` block returns the right
    transaction-scoped object.
    """
    from contextlib import asynccontextmanager

    from scheduler import jobs as jobs_mod
    from services.auth.jwt_rotation import rotate_tenant_key

    await rotate_tenant_key(_session, tenant_id=1)
    await rotate_tenant_key(_session, tenant_id=1)
    retiring = (
        await _session.exec(
            select(TenantSigningKey).where(
                TenantSigningKey.status == TenantSigningKeyStatus.RETIRING
            )
        )
    ).one()
    retiring.retired_at = datetime.now(UTC) - timedelta(days=14)
    await _session.commit()

    @asynccontextmanager
    async def _yield_session():
        yield _session

    import db.session as db_session_mod

    orig = db_session_mod.async_session
    db_session_mod.async_session = _yield_session
    jobs_mod.async_session = _yield_session
    try:
        await jobs_mod.expire_retiring_signing_keys()
    finally:
        db_session_mod.async_session = orig
        jobs_mod.async_session = orig

    # The cron flipped the backdated RETIRING row to RETIRED.
    row = (
        await _session.exec(select(TenantSigningKey).where(TenantSigningKey.id == retiring.id))
    ).one()
    assert row.status == TenantSigningKeyStatus.RETIRED
