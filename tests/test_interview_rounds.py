"""Interview rounds — plan 95 § 3.1 (slice 95d).

Rounds are entities WITHIN a stage: upsert idempotence (reminder spam never
duplicates), clubbed-onsite sessions merge, notes-plan projection, calendar
producer, stage derivation from completed rounds, and the board chip.
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

    from models import (
        AppEvent,
        Application,
        CalendarConnection,
        CalendarEvent,
        CompanyAlias,
        EmailAccount,
        EmailMessage,
        EmailThread,
        InterviewRound,
        Job,
        SenderRule,
        User,
    )

    tables = [
        User.__table__,
        Job.__table__,
        Application.__table__,
        AppEvent.__table__,
        EmailThread.__table__,
        EmailAccount.__table__,
        EmailMessage.__table__,
        CompanyAlias.__table__,
        SenderRule.__table__,
        InterviewRound.__table__,
        CalendarConnection.__table__,
        CalendarEvent.__table__,
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

    u = User(email="rounds@example.com", password_hash="x", is_active=True)
    session.add(u)
    await session.flush()
    return u


@pytest.fixture
async def application(session, user):
    from models import Application
    from models.enums import ApplicationStatus

    a = Application(
        user_id=user.id,
        company="Camber",
        role="Senior Software Engineer",
        status=ApplicationStatus.RECRUITER_SCREEN,
    )
    session.add(a)
    await session.flush()
    return a


# ── Upsert idempotence ──────────────────────────────────────────────────


async def test_three_reminders_stay_one_round(session, user, application):
    from services.applications import rounds

    for _ in range(3):
        await rounds.upsert_round(
            session,
            application=application,
            kind="technical_screen",
            source="email",
            state="scheduled",
        )
    rows = await rounds.list_rounds(session, application_id=application.id)
    assert len(rows) == 1
    assert rows[0].kind == "technical_screen"
    assert rows[0].state == "scheduled"


async def test_two_distinct_kinds_become_two_rounds(session, user, application):
    """Camber-style: technical screen AND system design — two checklist
    entries under ONE application (the § 6 acceptance)."""
    from services.applications import rounds

    await rounds.upsert_round(
        session, application=application, kind="technical_screen", source="email"
    )
    await rounds.upsert_round(
        session, application=application, kind="system_design", source="email"
    )
    rows = await rounds.list_rounds(session, application_id=application.id)
    assert [r.kind for r in rows] == ["technical_screen", "system_design"]
    assert [r.round_no for r in rows] == [1, 2]


async def test_dated_signal_fills_dateless_round_not_duplicates(session, user, application):
    from services.applications import rounds

    await rounds.upsert_round(
        session, application=application, kind="system_design", source="email"
    )
    when = datetime.now(UTC) + timedelta(days=3)
    await rounds.upsert_round(
        session,
        application=application,
        kind="system_design",
        source="calendar",
        scheduled_at=when,
    )
    rows = await rounds.list_rounds(session, application_id=application.id)
    assert len(rows) == 1
    assert rows[0].scheduled_at is not None


async def test_email_checks_off_planned_round(session, user, application):
    """Notes create planned rounds; a later email upsert ratchets the state
    forward (planned → scheduled) instead of duplicating."""
    from services.applications import rounds

    await rounds.create_planned_rounds(
        session,
        application=application,
        parsed_rounds=[{"kind": "hiring_manager", "title": "HM chat", "sessions": []}],
    )
    await rounds.upsert_round(
        session, application=application, kind="hiring_manager", source="email"
    )
    rows = await rounds.list_rounds(session, application_id=application.id)
    assert len(rows) == 1
    assert rows[0].state == "scheduled"
    assert rows[0].title == "HM chat"  # notes title survives


# ── Clubbed onsite loops ────────────────────────────────────────────────


async def test_clubbed_loop_sessions_merge_not_sibling_rounds(session, user, application):
    from services.applications import rounds

    await rounds.upsert_round(
        session,
        application=application,
        kind="onsite_loop",
        source="notes",
        state="planned",
        sessions=[{"title": "Coding"}, {"title": "System design"}],
    )
    await rounds.upsert_round(
        session,
        application=application,
        kind="onsite_loop",
        source="email",
        sessions=[{"title": "System design"}, {"title": "Behavioral with HM"}],
    )
    rows = await rounds.list_rounds(session, application_id=application.id)
    assert len(rows) == 1
    titles = [s["title"] for s in rows[0].sessions]
    assert titles == ["Coding", "System design", "Behavioral with HM"]


# ── Stage derivation ────────────────────────────────────────────────────


async def test_completed_onsite_kind_round_implies_interview_stage(session, user, application):
    """A completed system-design round pulls the application forward to
    ONSITE_LOOP through the same update_status path as email signal."""
    from models.enums import ApplicationStatus
    from services.applications import rounds

    row = await rounds.upsert_round(
        session, application=application, kind="system_design", source="email"
    )
    assert application.status == ApplicationStatus.RECRUITER_SCREEN

    await rounds.set_round_state(session, user_id=user.id, round_id=row.id, state="completed")
    await session.refresh(application)
    assert application.status == ApplicationStatus.ONSITE_LOOP


async def test_derivation_is_forward_only(session, user):
    """A completed recruiter screen never drags an ONSITE_LOOP application
    backward."""
    from models import Application
    from models.enums import ApplicationStatus
    from services.applications import rounds

    application = Application(
        user_id=user.id,
        company="Ripple",
        role="SWE",
        status=ApplicationStatus.ONSITE_LOOP,
    )
    session.add(application)
    await session.flush()

    row = await rounds.upsert_round(
        session, application=application, kind="recruiter_screen", source="email"
    )
    await rounds.set_round_state(session, user_id=user.id, round_id=row.id, state="completed")
    await session.refresh(application)
    assert application.status == ApplicationStatus.ONSITE_LOOP


async def test_set_round_state_idor(session, user, application):
    from models import User
    from services.applications import rounds

    other = User(email="other-r@example.com", password_hash="x", is_active=True)
    session.add(other)
    await session.flush()
    row = await rounds.upsert_round(session, application=application, kind="panel", source="manual")
    with pytest.raises(rounds.RoundError):
        await rounds.set_round_state(session, user_id=other.id, round_id=row.id, state="completed")


# ── Calendar producer ───────────────────────────────────────────────────


def test_round_kind_from_title():
    from services.applications import rounds

    assert rounds.round_kind_from_title("Virtual System Design Exercise") == "system_design"
    assert rounds.round_kind_from_title("Recruiter screen w/ Dana") == "recruiter_screen"
    assert rounds.round_kind_from_title("Camber onsite — final round") == "onsite_loop"
    assert rounds.round_kind_from_title("Interview with Ripple") == "other"
    assert rounds.round_kind_from_title("Dentist appointment") is None


async def test_calendar_event_upserts_scheduled_round(session, user, application):
    from models import CalendarEvent
    from services.applications import rounds as rounds_service
    from services.email.calendar_sync import _upsert_rounds_from_events

    event = CalendarEvent(
        user_id=user.id,
        connection_id=1,
        uid="ev-1",
        title="Camber — Virtual System Design Exercise",
        starts_at=datetime.now(UTC) + timedelta(days=2),
        matched_application_id=application.id,
    )
    session.add(event)
    await session.flush()

    await _upsert_rounds_from_events(session, events=[event])
    rows = await rounds_service.list_rounds(session, application_id=application.id)
    assert len(rows) == 1
    assert rows[0].kind == "system_design"
    assert rows[0].state == "scheduled"
    assert rows[0].calendar_event_id == event.id

    # Second sync of the same event: still one round.
    await _upsert_rounds_from_events(session, events=[event])
    assert len(await rounds_service.list_rounds(session, application_id=application.id)) == 1


# ── Email producer (classifier dispatch) ────────────────────────────────


async def test_classifier_round_kind_upserts_round(session, user, application, monkeypatch):
    from types import SimpleNamespace

    from models import EmailMessage, EmailThread
    from models.enums import EmailClassification
    from services.applications import rounds as rounds_service
    from services.email import classifier as email_classifier

    thread = EmailThread(
        user_id=user.id,
        provider="imap",
        thread_id_external="<t-camber@x>",
        subject="System design round",
        classification=EmailClassification.OTHER,
        latest_message_at=datetime.now(UTC),
        application_id=application.id,
    )
    session.add(thread)
    await session.flush()
    msg = EmailMessage(
        user_id=user.id,
        thread_id=thread.id,
        application_id=application.id,
        provider="imap",
        message_id_external="<m-camber@x>",
        sender_email="recruiting@camber.health",
        subject="Your system design round at Camber",
        snippet="Scheduling your virtual system design exercise.",
        received_at=datetime.now(UTC),
    )
    session.add(msg)
    await session.flush()

    class _FakeProvider:
        model = "stub"

    class _FakeStructured:
        def __init__(self, value):
            self.value = value

    async def _fake_get_settings(_session, *, user_id):
        return SimpleNamespace(user_id=user_id)

    async def _fake_tracked_call(**kwargs):
        return _FakeStructured(
            {
                "classification": "interview_request",
                "urgency": "high",
                "company": "Camber",
                "stage": "interview",
                "round_kind": "system_design",
                "sender_type": "employer",
            }
        )

    async def _no_notify(**kwargs):
        return None

    monkeypatch.setattr(email_classifier, "_get_settings", _fake_get_settings)
    monkeypatch.setattr(email_classifier, "get_provider", lambda _s: _FakeProvider())
    monkeypatch.setattr(email_classifier.llm_tracker, "tracked_call", _fake_tracked_call)
    monkeypatch.setattr(email_classifier.notify, "notify_priority_email", _no_notify)

    await email_classifier.classify_unprocessed(session)

    assert msg.extracted_round_kind == "system_design"
    rows = await rounds_service.list_rounds(session, application_id=application.id)
    assert len(rows) == 1
    assert rows[0].kind == "system_design"
    assert rows[0].email_message_id == msg.id


# ── Chip ────────────────────────────────────────────────────────────────


async def test_round_chip_shape(session, user, application):
    from services.applications import rounds

    assert rounds.round_chip([]) is None
    r1 = await rounds.upsert_round(
        session, application=application, kind="technical_screen", source="email"
    )
    await rounds.upsert_round(
        session,
        application=application,
        kind="system_design",
        source="notes",
        state="planned",
        title="Virtual System Design",
    )
    await rounds.set_round_state(session, user_id=user.id, round_id=r1.id, state="completed")
    rows = await rounds.list_rounds(session, application_id=application.id)
    assert rounds.round_chip(rows) == "1/2 · Virtual System Design"
