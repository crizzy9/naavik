"""Staleness sweep + going-quiet — plan 95 § 3.2 (slice 95e).

Silence as a signal: `last_signal_at` derived from the AppEvent log, snooze
honored via the JSONB slot, auto-close strictly opt-in.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles

os.environ.setdefault("NAAVIK_DEBUG", "1")

sqlite3.register_adapter(list, json.dumps)
sqlite3.register_adapter(dict, json.dumps)


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw):  # type: ignore[misc]
    return "TEXT"


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_type, _compiler, **_kw):  # type: ignore[misc]
    return "TEXT"


def _tables():
    from sqlalchemy import CheckConstraint

    from models import AppEvent, Application, Job, Settings, User

    tables = [
        User.__table__,
        Job.__table__,
        Application.__table__,
        AppEvent.__table__,
        Settings.__table__,
    ]
    for table in tables:
        for c in list(table.constraints):
            if isinstance(c, CheckConstraint):
                table.constraints.discard(c)
    return tables


@pytest.fixture
async def session():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool
    from sqlmodel.ext.asyncio.session import AsyncSession

    tables = _tables()
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        for table in tables:
            await conn.run_sync(table.create)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


@pytest.fixture
async def user(session):
    from models import User

    u = User(email="quiet@example.com", password_hash="x", is_active=True)
    session.add(u)
    await session.flush()
    return u


async def _seed_application(session, *, user_id: int, company: str, days_old: int, status=None):
    from models import Application
    from models.enums import ApplicationStatus

    when = datetime.now(UTC) - timedelta(days=days_old)
    a = Application(
        user_id=user_id,
        company=company,
        role="SWE",
        status=status or ApplicationStatus.RECRUITER_SCREEN,
        applied_at=when,
        created_at=when,
        updated_at=when,
    )
    session.add(a)
    await session.flush()
    return a


async def _seed_event(session, *, user_id: int, application_id: int, days_ago: int):
    from models import AppEvent
    from models.enums import AppEventKind

    ev = AppEvent(
        user_id=user_id,
        application_id=application_id,
        kind=AppEventKind.EMAIL_RECEIVED,
        payload={},
        occurred_at=datetime.now(UTC) - timedelta(days=days_ago),
    )
    session.add(ev)
    await session.flush()
    return ev


async def test_signal_derivation_from_event_log(session, user):
    """A recent AppEvent keeps an old application off the quiet list —
    last_signal_at is the event log's max, not the row's age."""
    from services.applications import staleness

    old_but_active = await _seed_application(session, user_id=user.id, company="A", days_old=60)
    await _seed_event(session, user_id=user.id, application_id=old_but_active.id, days_ago=3)
    truly_quiet = await _seed_application(session, user_id=user.id, company="B", days_old=45)
    await _seed_event(session, user_id=user.id, application_id=truly_quiet.id, days_ago=40)
    fresh = await _seed_application(session, user_id=user.id, company="C", days_old=5)

    quiet = await staleness.list_going_quiet(session, user_id=user.id, stale_days=30)
    assert [q.application.company for q in quiet] == ["B"]
    assert quiet[0].days_quiet == 40
    assert fresh.id not in [q.application.id for q in quiet]


async def test_closed_and_draft_excluded(session, user):
    from models.enums import ApplicationStatus
    from services.applications import staleness

    await _seed_application(
        session, user_id=user.id, company="Closed Co", days_old=90, status=ApplicationStatus.CLOSED
    )
    await _seed_application(
        session, user_id=user.id, company="Draft Co", days_old=90, status=ApplicationStatus.DRAFT
    )
    quiet = await staleness.list_going_quiet(session, user_id=user.id, stale_days=30)
    assert quiet == []


async def test_snooze_honored_and_expires(session, user):
    from services.applications import staleness

    a = await _seed_application(session, user_id=user.id, company="Snoozed", days_old=45)
    await staleness.snooze(session, user_id=user.id, application_id=a.id, days=14)

    quiet = await staleness.list_going_quiet(session, user_id=user.id, stale_days=30)
    assert quiet == []  # snooze hides it

    # 15 days later the snooze has lapsed — it resurfaces.
    later = datetime.now(UTC) + timedelta(days=15)
    quiet = await staleness.list_going_quiet(session, user_id=user.id, stale_days=30, now=later)
    assert [q.application.company for q in quiet] == ["Snoozed"]


async def test_sweep_counts_but_never_closes_by_default(session, user):
    from models import Settings
    from models.enums import ApplicationStatus
    from services.applications import staleness

    session.add(Settings(user_id=user.id))
    a = await _seed_application(session, user_id=user.id, company="Quiet Co", days_old=45)

    stats = await staleness.sweep(session)
    assert stats == {"flagged": 1, "auto_closed": 0}
    await session.refresh(a)
    assert a.status == ApplicationStatus.RECRUITER_SCREEN  # untouched


async def test_sweep_auto_close_opt_in(session, user):
    from models import Settings
    from models.enums import ApplicationStatus, ClosedReason
    from services.applications import staleness

    session.add(Settings(user_id=user.id, auto_close_ghosted_after_days=60))
    barely_quiet = await _seed_application(session, user_id=user.id, company="Barely", days_old=45)
    long_dead = await _seed_application(session, user_id=user.id, company="Dead", days_old=90)

    stats = await staleness.sweep(session)
    assert stats["auto_closed"] == 1
    await session.refresh(long_dead)
    await session.refresh(barely_quiet)
    assert long_dead.status == ApplicationStatus.CLOSED
    assert long_dead.closed_reason == ClosedReason.GHOSTED
    assert barely_quiet.status == ApplicationStatus.RECRUITER_SCREEN

    # Auto-close trail rides the single write path with the cleanup trigger.
    from sqlmodel import select

    from models import AppEvent
    from models.enums import AppEventKind

    events = (await session.exec(select(AppEvent))).all()
    closes = [
        e
        for e in events
        if e.kind == AppEventKind.STATUS_CHANGE and e.payload.get("to") == "CLOSED"
    ]
    assert len(closes) == 1
    assert closes[0].payload.get("trigger") == "cleanup_stale"


async def test_mark_ghosted_and_idor(session, user):
    from models import User
    from models.enums import ApplicationStatus, ClosedReason
    from services.applications import staleness

    a = await _seed_application(session, user_id=user.id, company="Ghosty", days_old=45)
    other = User(email="other-q@example.com", password_hash="x", is_active=True)
    session.add(other)
    await session.flush()

    with pytest.raises(staleness.StalenessError):
        await staleness.mark_ghosted(session, user_id=other.id, application_id=a.id)

    out = await staleness.mark_ghosted(session, user_id=user.id, application_id=a.id)
    assert out.status == ApplicationStatus.CLOSED
    assert out.closed_reason == ClosedReason.GHOSTED
