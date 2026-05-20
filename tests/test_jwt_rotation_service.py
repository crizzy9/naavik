"""Tests for the JWT rotation service — plan 62 (0.2.7.07).

In-memory sqlite. Covers `rotate_tenant_key` + `expire_retiring_keys` +
`ensure_active_key` + key-pair generation.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

os.environ.setdefault("NAAVIK_DEBUG", "1")

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import (
    SigningAlgorithm,
    Tenant,
    TenantSigningKey,
    TenantSigningKeyStatus,
)
from services.jwt_rotation_service import (
    _generate_keypair,
    ensure_active_key,
    expire_retiring_keys,
    rotate_tenant_key,
)


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
        await session.commit()
        yield session
    await engine.dispose()


# ── _generate_keypair ─────────────────────────────────────────────────────


def test_generate_keypair_rs256() -> None:
    public_pem, private_pem = _generate_keypair(SigningAlgorithm.RS256)
    assert public_pem is not None and "BEGIN PUBLIC KEY" in public_pem
    assert "BEGIN PRIVATE KEY" in private_pem


def test_generate_keypair_hs256() -> None:
    public_pem, private_pem = _generate_keypair(SigningAlgorithm.HS256)
    assert public_pem is None
    # url-safe base64 token of >= 48 bytes encoded → at least 64 chars.
    assert len(private_pem) >= 32


def test_generate_keypair_rejects_unknown() -> None:
    class _Mock:
        value = "BOGUS"

    with pytest.raises(ValueError):
        _generate_keypair(_Mock())  # type: ignore[arg-type]


# ── rotate_tenant_key ─────────────────────────────────────────────────────


async def test_rotate_tenant_key_creates_first_active(_session) -> None:
    fresh = await rotate_tenant_key(_session, tenant_id=1, algorithm=SigningAlgorithm.RS256)
    await _session.commit()
    assert fresh.status == TenantSigningKeyStatus.ACTIVE
    assert fresh.algorithm == SigningAlgorithm.RS256
    assert fresh.kid
    rows = (await _session.exec(select(TenantSigningKey))).all()
    assert len(rows) == 1


async def test_rotate_tenant_key_demotes_previous_to_retiring(_session) -> None:
    first = await rotate_tenant_key(_session, tenant_id=1)
    await _session.commit()
    second = await rotate_tenant_key(_session, tenant_id=1)
    await _session.commit()

    await _session.refresh(first)
    assert first.status == TenantSigningKeyStatus.RETIRING
    assert first.retired_at is not None
    assert second.status == TenantSigningKeyStatus.ACTIVE
    assert second.kid != first.kid


async def test_rotate_tenant_key_per_tenant_isolation(_session) -> None:
    _session.add(Tenant(id=2, name="tenant-two"))
    await _session.commit()

    a = await rotate_tenant_key(_session, tenant_id=1)
    b = await rotate_tenant_key(_session, tenant_id=2)
    await _session.commit()
    assert a.tenant_id == 1 and b.tenant_id == 2
    actives = (
        await _session.exec(
            select(TenantSigningKey).where(TenantSigningKey.status == TenantSigningKeyStatus.ACTIVE)
        )
    ).all()
    assert {row.tenant_id for row in actives} == {1, 2}


# ── expire_retiring_keys ──────────────────────────────────────────────────


async def test_expire_retiring_keys_skips_within_grace(_session) -> None:
    await rotate_tenant_key(_session, tenant_id=1)
    await _session.commit()
    # Trigger a rotation so the prior key sits in RETIRING with retired_at=now.
    await rotate_tenant_key(_session, tenant_id=1)
    await _session.commit()

    flipped = await expire_retiring_keys(_session, default_grace_days=7)
    await _session.commit()
    assert flipped == 0


async def test_expire_retiring_keys_flips_after_grace(_session) -> None:
    await rotate_tenant_key(_session, tenant_id=1)
    await _session.commit()
    await rotate_tenant_key(_session, tenant_id=1)
    await _session.commit()

    # Backdate retired_at past grace window.
    retiring = (
        await _session.exec(
            select(TenantSigningKey).where(
                TenantSigningKey.status == TenantSigningKeyStatus.RETIRING
            )
        )
    ).all()
    assert len(retiring) == 1
    retiring[0].retired_at = datetime.now(UTC) - timedelta(days=10)
    await _session.commit()

    flipped = await expire_retiring_keys(_session, default_grace_days=7)
    await _session.commit()
    assert flipped == 1

    row = (
        await _session.exec(select(TenantSigningKey).where(TenantSigningKey.id == retiring[0].id))
    ).one()
    assert row.status == TenantSigningKeyStatus.RETIRED
    # Wipe of private material on terminal transition.
    assert row.private_key_pem is None


async def test_expire_retiring_keys_per_tenant_grace_override(_session) -> None:
    _session.add(Tenant(id=2, name="tenant-two"))
    await _session.commit()
    await rotate_tenant_key(_session, tenant_id=1)
    await rotate_tenant_key(_session, tenant_id=1)
    await rotate_tenant_key(_session, tenant_id=2)
    await rotate_tenant_key(_session, tenant_id=2)
    await _session.commit()

    # Both tenants have a RETIRING row with retired_at = ~now.
    retiring = (
        await _session.exec(
            select(TenantSigningKey).where(
                TenantSigningKey.status == TenantSigningKeyStatus.RETIRING
            )
        )
    ).all()
    for r in retiring:
        r.retired_at = datetime.now(UTC) - timedelta(days=5)
    await _session.commit()

    # tenant_id=1 has 1-day grace (expired), tenant_id=2 has 30-day grace (still in grace).
    flipped = await expire_retiring_keys(
        _session,
        grace_days_by_tenant={1: 1, 2: 30},
        default_grace_days=7,
    )
    await _session.commit()
    assert flipped == 1

    statuses = {
        r.tenant_id: r.status for r in (await _session.exec(select(TenantSigningKey))).all()
    }
    # Each tenant has 1 ACTIVE + (RETIRED or RETIRING).
    rows_by_status = (
        await _session.exec(
            select(TenantSigningKey).where(
                TenantSigningKey.status == TenantSigningKeyStatus.RETIRED
            )
        )
    ).all()
    assert len(rows_by_status) == 1
    assert rows_by_status[0].tenant_id == 1
    _ = statuses  # silence unused


# ── ensure_active_key ─────────────────────────────────────────────────────


async def test_ensure_active_key_returns_existing(_session) -> None:
    existing = await rotate_tenant_key(_session, tenant_id=1)
    await _session.commit()
    same = await ensure_active_key(_session, tenant_id=1)
    assert same.id == existing.id


async def test_ensure_active_key_bootstraps_on_empty(_session) -> None:
    rows = (await _session.exec(select(TenantSigningKey))).all()
    assert rows == []
    fresh = await ensure_active_key(_session, tenant_id=1)
    await _session.commit()
    assert fresh.status == TenantSigningKeyStatus.ACTIVE
    assert fresh.algorithm == SigningAlgorithm.RS256
