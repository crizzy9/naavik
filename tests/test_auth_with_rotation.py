"""End-to-end rotation integration — plan 62 (0.2.7.07).

In-memory sqlite. Issues a JWT under the active key, rotates, asserts:

1. Pre-rotation token still verifies during the grace window.
2. Expiring the now-RETIRING row beyond its grace flips it RETIRED →
   verification rejects.
3. The newly-issued ACTIVE key's tokens verify cleanly.
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
from services.auth import issue_jwt_async, verify_jwt_async
from services.jwt_rotation_service import expire_retiring_keys, rotate_tenant_key

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
        await session.commit()
        yield session
    await engine.dispose()


async def test_token_survives_rotation_within_grace(_session) -> None:
    await rotate_tenant_key(_session, tenant_id=1, algorithm=SigningAlgorithm.RS256)
    await _session.commit()

    pre_token = await issue_jwt_async(_session, user_id=42, tenant_id=1)
    assert await verify_jwt_async(_session, pre_token, tenant_id=1) is not None

    # Rotate — pre_token's kid now points at a RETIRING row.
    await rotate_tenant_key(_session, tenant_id=1)
    await _session.commit()

    # Token still verifies — grace window covers it.
    assert await verify_jwt_async(_session, pre_token, tenant_id=1) is not None


async def test_token_rejected_after_retiring_expires(_session) -> None:
    await rotate_tenant_key(_session, tenant_id=1, algorithm=SigningAlgorithm.RS256)
    await _session.commit()

    pre_token = await issue_jwt_async(_session, user_id=42, tenant_id=1)

    # Rotate, then backdate the RETIRING row past grace + run sweep.
    await rotate_tenant_key(_session, tenant_id=1)
    await _session.commit()

    retiring = (
        await _session.exec(
            select(TenantSigningKey).where(
                TenantSigningKey.status == TenantSigningKeyStatus.RETIRING
            )
        )
    ).one()
    retiring.retired_at = datetime.now(UTC) - timedelta(days=14)
    await _session.commit()

    flipped = await expire_retiring_keys(_session, default_grace_days=7)
    await _session.commit()
    assert flipped == 1

    assert await verify_jwt_async(_session, pre_token, tenant_id=1) is None


async def test_post_rotation_token_verifies(_session) -> None:
    await rotate_tenant_key(_session, tenant_id=1, algorithm=SigningAlgorithm.RS256)
    await _session.commit()
    await rotate_tenant_key(_session, tenant_id=1)
    await _session.commit()

    fresh_token = await issue_jwt_async(_session, user_id=42, tenant_id=1)
    result = await verify_jwt_async(_session, fresh_token, tenant_id=1)
    assert result is not None
    assert result[0] == 42


async def test_tenant_isolation_under_rotation(_session) -> None:
    _session.add(Tenant(id=2, name="tenant-two"))
    await _session.commit()

    await rotate_tenant_key(_session, tenant_id=1)
    await rotate_tenant_key(_session, tenant_id=2)
    await _session.commit()

    t1_token = await issue_jwt_async(_session, user_id=10, tenant_id=1)
    t2_token = await issue_jwt_async(_session, user_id=20, tenant_id=2)

    # Cross-tenant verify rejects.
    assert await verify_jwt_async(_session, t1_token, tenant_id=2) is None
    assert await verify_jwt_async(_session, t2_token, tenant_id=1) is None
    # Same-tenant verify accepts.
    assert await verify_jwt_async(_session, t1_token, tenant_id=1) is not None
    assert await verify_jwt_async(_session, t2_token, tenant_id=2) is not None
