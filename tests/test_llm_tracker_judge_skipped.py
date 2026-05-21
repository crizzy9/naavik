"""Tests for `llm_tracker.judge_skipped_count_today` +
`judge_skipped_reasons_today` (plan 74 / 0.3.2.04).

Mirrors the sqlite-fixture pattern from `tests/test_service_layer_parity.py`:
in-memory `sqlite+aiosqlite:///:memory:` w/ JSONB compiled to TEXT so DDL
works. `judge_skipped` is a JSONB sub-key on `Job.match_breakdown`; the
helpers under test branch on dialect (`postgresql` uses `->>` operator;
non-Postgres falls back to a Python-side filter) so the sqlite path is
exercised here.
"""

from __future__ import annotations

import os  # noqa: I001

os.environ.setdefault("NAAVIK_DEBUG", "1")
os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")

from datetime import UTC, datetime, timedelta  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy import CheckConstraint  # noqa: E402
from sqlalchemy.dialects.postgresql import ARRAY, JSONB  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402
from sqlmodel.ext.asyncio.session import AsyncSession  # noqa: E402


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw):  # type: ignore[misc]
    return "TEXT"


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_type, _compiler, **_kw):  # type: ignore[misc]
    return "TEXT"


# Patch the ARRAY column type to JSON-encode lists for sqlite — sqlite3 can't
# bind a Python list. Mirrors the `_compile_array_sqlite` TEXT shim. Bind-side
# only; we never read these columns back in this test module.
import json  # noqa: E402

from sqlalchemy.dialects.postgresql.array import ARRAY as _PGARRAY  # noqa: E402


def _list_bind_processor(self, dialect):  # type: ignore[no-untyped-def]
    if dialect.name != "sqlite":
        return None

    def _process(value):
        if value is None:
            return None
        return json.dumps(list(value))

    return _process


_PGARRAY.bind_processor = _list_bind_processor  # type: ignore[method-assign]


from models import ApplicationBoard, Job, JobSource, User  # noqa: E402
from models.enums import JobQueueState, RemotePolicy, VisaRestriction  # noqa: E402
from services import llm_tracker  # noqa: E402


def _strip_pg_checks() -> list:
    """User + Job tables minus Postgres-only CHECK / GIN constructs."""
    tables = [User.__table__, Job.__table__]
    for t in tables:
        bad = [
            c
            for c in list(t.constraints)
            if isinstance(c, CheckConstraint) and "char_length" in str(c.sqltext)
        ]
        for c in bad:
            t.constraints.discard(c)
        bad_idx = [i for i in list(t.indexes) if "gin" in (i.name or "").lower()]
        for i in bad_idx:
            t.indexes.discard(i)
    return tables


_TABLES = _strip_pg_checks()


@pytest.fixture
async def session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(lambda sc: SQLModel.metadata.create_all(sc, tables=_TABLES))
    sm = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sm() as s:
        yield s
    await engine.dispose()


def _today_midnight_utc() -> datetime:
    return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


async def _seed_user(session: AsyncSession, user_id: int = 1) -> User:
    u = User(
        id=user_id,
        email=f"user{user_id}@local",
        password_hash="$2b$04$placeholder",
        is_active=True,
        must_change_password=False,
    )
    session.add(u)
    await session.flush()
    return u


_JOB_COUNTER = {"n": 0}


def _next_external_id() -> str:
    _JOB_COUNTER["n"] += 1
    return f"ext-{_JOB_COUNTER['n']:08d}"


async def _seed_job(
    session: AsyncSession,
    *,
    user_id: int,
    judge_skipped: bool,
    judge_skipped_reason: str | None,
    updated_at: datetime,
    deleted_at: datetime | None = None,
) -> Job:
    breakdown: dict = {
        "score": 0.6,
        "judge_skipped": judge_skipped,
        "judge_skipped_reason": judge_skipped_reason,
    }
    eid = _next_external_id()
    job = Job(
        user_id=user_id,
        source=JobSource.LINKEDIN,
        board=ApplicationBoard.LINKEDIN,
        external_id=eid,
        url=f"https://example.test/jobs/{eid}",
        url_type="canonical",
        company="Acme",
        role="SWE",
        description="x" * 32,
        remote_policy=RemotePolicy.UNKNOWN,
        visa_restrictions=VisaRestriction.NOT_MENTIONED,
        score=0.6,
        match_breakdown=breakdown,
        queue_state=JobQueueState.UNSWIPED,
        updated_at=updated_at,
        deleted_at=deleted_at,
    )
    session.add(job)
    await session.flush()
    return job


# ── judge_skipped_count_today ─────────────────────────────────────────


async def test_count_zero_when_no_jobs(session: AsyncSession) -> None:
    await _seed_user(session)
    assert await llm_tracker.judge_skipped_count_today(session, user_id=1) == 0


async def test_count_zero_when_no_skips_today(session: AsyncSession) -> None:
    await _seed_user(session)
    midnight = _today_midnight_utc()
    await _seed_job(
        session,
        user_id=1,
        judge_skipped=False,
        judge_skipped_reason=None,
        updated_at=midnight + timedelta(hours=2),
    )
    await _seed_job(
        session,
        user_id=1,
        judge_skipped=False,
        judge_skipped_reason=None,
        updated_at=midnight + timedelta(hours=5),
    )
    assert await llm_tracker.judge_skipped_count_today(session, user_id=1) == 0


async def test_count_matches_skipped_rows(session: AsyncSession) -> None:
    await _seed_user(session)
    midnight = _today_midnight_utc()
    for _ in range(3):
        await _seed_job(
            session,
            user_id=1,
            judge_skipped=True,
            judge_skipped_reason="cost_cap_exhausted",
            updated_at=midnight + timedelta(hours=1),
        )
    await _seed_job(
        session,
        user_id=1,
        judge_skipped=False,
        judge_skipped_reason=None,
        updated_at=midnight + timedelta(hours=2),
    )
    assert await llm_tracker.judge_skipped_count_today(session, user_id=1) == 3


async def test_count_excludes_yesterday(session: AsyncSession) -> None:
    await _seed_user(session)
    midnight = _today_midnight_utc()
    yesterday = midnight - timedelta(days=1, hours=3)
    await _seed_job(
        session,
        user_id=1,
        judge_skipped=True,
        judge_skipped_reason="cost_cap_exhausted",
        updated_at=yesterday,
    )
    await _seed_job(
        session,
        user_id=1,
        judge_skipped=True,
        judge_skipped_reason="cost_cap_exhausted",
        updated_at=midnight + timedelta(minutes=10),
    )
    assert await llm_tracker.judge_skipped_count_today(session, user_id=1) == 1


async def test_count_excludes_soft_deleted(session: AsyncSession) -> None:
    await _seed_user(session)
    midnight = _today_midnight_utc()
    await _seed_job(
        session,
        user_id=1,
        judge_skipped=True,
        judge_skipped_reason="cost_cap_exhausted",
        updated_at=midnight + timedelta(hours=1),
        deleted_at=midnight + timedelta(hours=2),
    )
    await _seed_job(
        session,
        user_id=1,
        judge_skipped=True,
        judge_skipped_reason="cost_cap_exhausted",
        updated_at=midnight + timedelta(hours=3),
    )
    assert await llm_tracker.judge_skipped_count_today(session, user_id=1) == 1


async def test_count_idor_per_user(session: AsyncSession) -> None:
    await _seed_user(session, user_id=1)
    await _seed_user(session, user_id=2)
    midnight = _today_midnight_utc()
    for _ in range(2):
        await _seed_job(
            session,
            user_id=1,
            judge_skipped=True,
            judge_skipped_reason="cost_cap_exhausted",
            updated_at=midnight + timedelta(hours=1),
        )
    for _ in range(5):
        await _seed_job(
            session,
            user_id=2,
            judge_skipped=True,
            judge_skipped_reason="no_provider_configured",
            updated_at=midnight + timedelta(hours=1),
        )
    assert await llm_tracker.judge_skipped_count_today(session, user_id=1) == 2
    assert await llm_tracker.judge_skipped_count_today(session, user_id=2) == 5


# ── judge_skipped_reasons_today ───────────────────────────────────────


async def test_reasons_empty_when_no_skips(session: AsyncSession) -> None:
    await _seed_user(session)
    assert await llm_tracker.judge_skipped_reasons_today(session, user_id=1) == {}


async def test_reasons_distribution_grouped(session: AsyncSession) -> None:
    await _seed_user(session)
    midnight = _today_midnight_utc()
    for _ in range(4):
        await _seed_job(
            session,
            user_id=1,
            judge_skipped=True,
            judge_skipped_reason="cost_cap_exhausted",
            updated_at=midnight + timedelta(hours=1),
        )
    for _ in range(2):
        await _seed_job(
            session,
            user_id=1,
            judge_skipped=True,
            judge_skipped_reason="no_provider_configured",
            updated_at=midnight + timedelta(hours=1),
        )
    reasons = await llm_tracker.judge_skipped_reasons_today(session, user_id=1)
    assert reasons == {"cost_cap_exhausted": 4, "no_provider_configured": 2}


async def test_reasons_excludes_yesterday(session: AsyncSession) -> None:
    await _seed_user(session)
    midnight = _today_midnight_utc()
    await _seed_job(
        session,
        user_id=1,
        judge_skipped=True,
        judge_skipped_reason="cost_cap_exhausted",
        updated_at=midnight - timedelta(days=1, hours=2),
    )
    await _seed_job(
        session,
        user_id=1,
        judge_skipped=True,
        judge_skipped_reason="no_provider_configured",
        updated_at=midnight + timedelta(hours=1),
    )
    reasons = await llm_tracker.judge_skipped_reasons_today(session, user_id=1)
    assert reasons == {"no_provider_configured": 1}


async def test_reasons_idor_per_user(session: AsyncSession) -> None:
    await _seed_user(session, user_id=1)
    await _seed_user(session, user_id=2)
    midnight = _today_midnight_utc()
    await _seed_job(
        session,
        user_id=1,
        judge_skipped=True,
        judge_skipped_reason="cost_cap_exhausted",
        updated_at=midnight + timedelta(hours=1),
    )
    await _seed_job(
        session,
        user_id=2,
        judge_skipped=True,
        judge_skipped_reason="no_provider_configured",
        updated_at=midnight + timedelta(hours=1),
    )
    reasons_1 = await llm_tracker.judge_skipped_reasons_today(session, user_id=1)
    reasons_2 = await llm_tracker.judge_skipped_reasons_today(session, user_id=2)
    assert reasons_1 == {"cost_cap_exhausted": 1}
    assert reasons_2 == {"no_provider_configured": 1}


# ── Plan 75 / 0.3.3.17 — JSONB predicate lowercase hardening ─────────────


def test_judge_skipped_count_postgres_predicate_uses_lower():
    """Compile-time assertion: the Postgres branch wraps `->>` in `lower(...)`.

    Defense-in-depth — current writers always emit "true", but if a future
    JSONB write sneaks in "True" / "TRUE", the predicate stays correct.
    """
    from sqlalchemy import func
    from sqlalchemy import select as sa_select
    from sqlalchemy.dialects import postgresql

    from models import Job
    from services.llm_tracker import _today_midnight_utc

    midnight = _today_midnight_utc()
    stmt = sa_select(func.count(Job.id)).where(
        Job.user_id == 1,
        Job.deleted_at.is_(None),
        Job.updated_at >= midnight,
        func.lower(Job.match_breakdown.op("->>")("judge_skipped")) == "true",
    )
    compiled = str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "lower(" in compiled.lower(), (
        f"Postgres branch must wrap the JSONB extract in lower(); emitted SQL: {compiled}"
    )
