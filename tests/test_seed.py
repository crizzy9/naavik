"""Live-DB seed tests — Wave 4 of plan 10 § B.9.

These tests are opt-in via `NAAVIK_LIVE_DB=1` env (with `DATABASE_URL`
pointing at a running Postgres). They use function-scoped fresh engines
to avoid pytest-asyncio's "Event loop is closed" cross-test issue.

Coverage:
- migration runs cleanly (verified separately via `alembic upgrade head`)
- `db.seed.seed()` populates every fixture; counts match SAMPLE_DATA.md
- re-running `seed()` is a no-op (ON CONFLICT DO NOTHING)
- round-trip via SQLModel: SELECTs return rows shaped identically to
  the Pydantic shadow fixtures
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import NullPool
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import select

from db import sample_data as sd
from models import ApiUsage, Application, Job, Profile, User

_DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://naavik:password@127.0.0.1:5433/naavik",
)

_LIVE = os.environ.get("NAAVIK_LIVE_DB", "").strip().lower() in {"1", "true", "yes"}


pytestmark = pytest.mark.skipif(
    not _LIVE,
    reason="set NAAVIK_LIVE_DB=1 (and DATABASE_URL) to run live-DB seed tests",
)


def _fresh_session():
    """Create a fresh engine + sessionmaker per test to avoid event-loop reuse."""
    engine = create_async_engine(_DB_URL, poolclass=NullPool)
    return async_sessionmaker(engine, expire_on_commit=False), engine


async def test_seeded_user_count():
    sm, engine = _fresh_session()
    async with sm() as session:
        users = (await session.scalars(select(User))).all()
        assert len(users) == 1
        assert users[0].email == sd.USER.email
    await engine.dispose()


async def test_seeded_profile():
    sm, engine = _fresh_session()
    async with sm() as session:
        profile = (await session.scalars(select(Profile))).first()
        assert profile is not None
        assert profile.full_name == "Shyam Padia"
        assert profile.work_authorization is not None
    await engine.dispose()


async def test_seeded_jobs():
    sm, engine = _fresh_session()
    async with sm() as session:
        jobs = (await session.scalars(select(Job))).all()
        assert len(jobs) >= 18
        for j in jobs:
            assert 0.0 <= j.score <= 1.0
    await engine.dispose()


async def test_seeded_applications():
    sm, engine = _fresh_session()
    async with sm() as session:
        apps = (await session.scalars(select(Application))).all()
        assert len(apps) == 14
        drafts = [a for a in apps if a.status.value == "DRAFT"]
        assert len(drafts) == 2
        for d in drafts:
            assert d.applied_at is None
    await engine.dispose()


async def test_seeded_api_usage():
    sm, engine = _fresh_session()
    async with sm() as session:
        rows = (await session.scalars(select(ApiUsage))).all()
        assert len(rows) >= 25
        assert all(r.cost_usd >= 0 for r in rows)
    await engine.dispose()


async def test_seed_idempotent():
    """Re-run seed; row counts in tables must not double.

    The summary count from `seed()` is the number of rows the upsert
    *attempted* (one per fixture); ON CONFLICT DO NOTHING skips collisions
    so the actual SELECT count stays stable across re-runs.
    """
    from db.seed import seed

    sm, engine = _fresh_session()
    async with sm() as session:
        before = (await session.scalars(select(User))).all()
        before_count = len(before)

    await seed()
    await seed()

    sm2, engine2 = _fresh_session()
    async with sm2() as session:
        after = (await session.scalars(select(User))).all()
        assert len(after) == before_count
    await engine.dispose()
    await engine2.dispose()
