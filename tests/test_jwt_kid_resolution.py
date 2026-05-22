"""kid resolution + dual-key grace verify + reject scenarios — plan 62.

Covers the `verify_jwt_async` decision tree:

1. No kid header / kid='env-legacy' → legacy HS256 verify against SECRET_KEY.
2. Unknown kid → reject.
3. Known kid + ACTIVE → accept.
4. Known kid + RETIRING (grace) → accept.
5. Known kid + RETIRED → reject.
6. kid pointing at another tenant → reject (forged-kid attack).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

os.environ.setdefault("NAAVIK_DEBUG", "1")

import jwt as pyjwt
import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from config import settings as app_settings
from models import (
    SigningAlgorithm,
    Tenant,
    TenantSigningKey,
    TenantSigningKeyStatus,
)
from services.auth import (
    ENV_LEGACY_KID,
    JWT_ALGORITHM,
    issue_jwt,
    issue_jwt_async,
    verify_jwt,
    verify_jwt_async,
)
from services.jwt_rotation_service import rotate_tenant_key

pytestmark = pytest.mark.uses_sample_data_shims


@pytest.fixture
async def _session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: SQLModel.metadata.create_all(
                sync_conn,
                tables=[Tenant.__table__, TenantSigningKey.__table__],
            )
        )
    sm = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sm() as session:
        session.add(Tenant(id=1, name="self-hosted"))
        session.add(Tenant(id=2, name="tenant-two"))
        await session.commit()
        yield session
    await engine.dispose()


def _build_token(payload: dict, *, secret: str, kid: str | None) -> str:
    headers = {"kid": kid} if kid is not None else None
    return pyjwt.encode(payload, secret, algorithm=JWT_ALGORITHM, headers=headers)


# ── Legacy path: no kid header / env-legacy ──────────────────────────────


async def test_verify_jwt_async_no_kid_header_falls_back_to_legacy(_session) -> None:
    payload = {
        "sub": "42",
        "tid": "1",
        "jti": "fixed-jti-1234567890123456",
        "iat": int(datetime.now(UTC).timestamp()),
        "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
    }
    token = pyjwt.encode(payload, app_settings.secret_key, algorithm=JWT_ALGORITHM)
    result = await verify_jwt_async(_session, token)
    assert result is not None
    user_id, jti, _ = result
    assert user_id == 42 and jti == "fixed-jti-1234567890123456"


async def test_verify_jwt_async_env_legacy_kid_falls_back_to_legacy(_session) -> None:
    token = issue_jwt(42, keep_signed_in=False)
    header = pyjwt.get_unverified_header(token)
    assert header["kid"] == ENV_LEGACY_KID
    result = await verify_jwt_async(_session, token)
    assert result is not None
    assert result[0] == 42


def test_verify_jwt_sync_rejects_foreign_kid() -> None:
    """Sync legacy verifier must reject `kid` values it can't verify against
    SECRET_KEY — those tokens belong to the async path."""
    payload = {
        "sub": "42",
        "tid": "1",
        "jti": "fixed-jti-1234567890123456",
        "iat": int(datetime.now(UTC).timestamp()),
        "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
    }
    forged = _build_token(payload, secret=app_settings.secret_key, kid="rotated-kid")
    assert verify_jwt(forged) is None


# ── Unknown kid → reject ──────────────────────────────────────────────────


async def test_verify_jwt_async_unknown_kid_rejects(_session) -> None:
    # Token signed by SECRET_KEY but carrying a kid that doesn't exist in DB.
    payload = {
        "sub": "42",
        "tid": "1",
        "jti": "fixed-jti-1234567890123456",
        "iat": int(datetime.now(UTC).timestamp()),
        "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
    }
    forged = _build_token(payload, secret=app_settings.secret_key, kid="totally-unknown-kid")
    assert await verify_jwt_async(_session, forged) is None


# ── ACTIVE kid → accept ──────────────────────────────────────────────────


async def test_verify_jwt_async_active_key_accepts(_session) -> None:
    await rotate_tenant_key(_session, tenant_id=1, algorithm=SigningAlgorithm.RS256)
    await _session.commit()
    token = await issue_jwt_async(_session, user_id=42, tenant_id=1)
    result = await verify_jwt_async(_session, token, tenant_id=1)
    assert result is not None
    assert result[0] == 42


# ── RETIRING (grace) kid → accept ─────────────────────────────────────────


async def test_verify_jwt_async_grace_key_accepts(_session) -> None:
    # Issue token with first ACTIVE key, then rotate. Old key → RETIRING.
    await rotate_tenant_key(_session, tenant_id=1)
    await _session.commit()
    token = await issue_jwt_async(_session, user_id=42, tenant_id=1)
    await rotate_tenant_key(_session, tenant_id=1)
    await _session.commit()

    # Token's kid now points at a RETIRING row; verifier still accepts.
    result = await verify_jwt_async(_session, token, tenant_id=1)
    assert result is not None
    assert result[0] == 42


# ── RETIRED kid → reject ─────────────────────────────────────────────────


async def test_verify_jwt_async_retired_key_rejects(_session) -> None:
    await rotate_tenant_key(_session, tenant_id=1)
    await _session.commit()
    token = await issue_jwt_async(_session, user_id=42, tenant_id=1)

    # Flip the issuing key to RETIRED.
    from sqlmodel import select

    row = (
        await _session.exec(
            select(TenantSigningKey).where(
                TenantSigningKey.tenant_id == 1,
                TenantSigningKey.status == TenantSigningKeyStatus.ACTIVE,
            )
        )
    ).one()
    row.status = TenantSigningKeyStatus.RETIRED
    await _session.commit()

    assert await verify_jwt_async(_session, token, tenant_id=1) is None


# ── Cross-tenant kid (forged-kid attack) → reject ────────────────────────


async def test_verify_jwt_async_forged_kid_cross_tenant_rejects(_session) -> None:
    # Both tenants get an ACTIVE key.
    await rotate_tenant_key(_session, tenant_id=1)
    await rotate_tenant_key(_session, tenant_id=2)
    await _session.commit()

    # Token signed under tenant 2's key, but the verifier is asked to
    # validate it as tenant 1's session.
    token = await issue_jwt_async(_session, user_id=42, tenant_id=2)
    assert await verify_jwt_async(_session, token, tenant_id=1) is None
    # But verifying as tenant 2 works.
    assert await verify_jwt_async(_session, token, tenant_id=2) is not None


# ── Missing claim → reject ────────────────────────────────────────────────


async def test_verify_jwt_async_missing_sub_rejects(_session) -> None:
    await rotate_tenant_key(_session, tenant_id=1)
    await _session.commit()

    from sqlmodel import select

    key = (
        await _session.exec(
            select(TenantSigningKey).where(
                TenantSigningKey.tenant_id == 1,
                TenantSigningKey.status == TenantSigningKeyStatus.ACTIVE,
            )
        )
    ).one()

    payload = {
        "tid": "1",
        "jti": "j-no-sub",
        "iat": int(datetime.now(UTC).timestamp()),
        "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
    }
    token = pyjwt.encode(payload, key.private_key_pem, algorithm="RS256", headers={"kid": key.kid})
    assert await verify_jwt_async(_session, token, tenant_id=1) is None


# ── Issued JWT carries kid header ────────────────────────────────────────


async def test_issue_jwt_async_sets_kid_header(_session) -> None:
    fresh = await rotate_tenant_key(_session, tenant_id=1)
    await _session.commit()
    token = await issue_jwt_async(_session, user_id=42, tenant_id=1)
    header = pyjwt.get_unverified_header(token)
    assert header["kid"] == fresh.kid
    assert header["alg"] == "RS256"


async def test_issue_jwt_async_falls_back_when_no_active_key(_session) -> None:
    """If no ACTIVE key exists for the tenant, async path delegates to the
    sync legacy issuer (kid='env-legacy', HS256 + SECRET_KEY)."""
    token = await issue_jwt_async(_session, user_id=42, tenant_id=1)
    header = pyjwt.get_unverified_header(token)
    assert header["kid"] == ENV_LEGACY_KID
    assert header["alg"] == JWT_ALGORITHM
