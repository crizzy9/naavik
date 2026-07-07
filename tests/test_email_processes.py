"""Detected interview processes — 2026-07 tracking redesign.

Classified-but-unlinked messages group per company; the user opts in
("Track it") to pull the whole email timeline into the pipeline at the
inferred stage, or dismisses the group.
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

# Job carries ARRAY/JSONB columns; on the sqlite substrate they render as
# TEXT and lists/dicts bind via json (same shim as the inference tests).
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
        EmailAccount,
        EmailMessage,
        EmailThread,
        Job,
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

    u = User(email="proc@example.com", password_hash="x", is_active=True)
    session.add(u)
    await session.flush()
    return u


async def _seed_signal(
    session,
    *,
    user_id: int,
    company: str,
    classification,
    stage: str | None = None,
    role: str | None = None,
    offset_days: int = 0,
    subject: str = "Interview with you",
):
    from models import EmailMessage, EmailThread
    from models.enums import EmailClassification

    when = datetime.now(UTC) - timedelta(days=offset_days)
    thread = EmailThread(
        user_id=user_id,
        provider="imap",
        thread_id_external=f"<t-{company}-{offset_days}@example.com>",
        subject=subject,
        classification=EmailClassification.OTHER,
        latest_message_at=when,
    )
    session.add(thread)
    await session.flush()
    msg = EmailMessage(
        user_id=user_id,
        thread_id=thread.id,
        provider="imap",
        message_id_external=f"<m-{company}-{offset_days}@example.com>",
        sender_email="scheduler@example.com",
        subject=subject,
        snippet="…",
        received_at=when,
        classification=classification,
        extracted_company=company,
        extracted_role=role,
        extracted_stage=stage,
        classification_at=when,
    )
    session.add(msg)
    await session.flush()
    return msg


async def test_detects_processes_grouped_by_company(session, user):
    from models.enums import ApplicationStatus, EmailClassification
    from services.email import processes

    await _seed_signal(
        session,
        user_id=user.id,
        company="Ripple",
        classification=EmailClassification.INTERVIEW_REQUEST,
        stage="interview",
        role="Senior Software Engineer",
        offset_days=1,
    )
    await _seed_signal(
        session,
        user_id=user.id,
        company="ripple",  # case-insensitive grouping
        classification=EmailClassification.INTERVIEW_REQUEST,
        stage=None,
        offset_days=3,
    )
    await _seed_signal(
        session,
        user_id=user.id,
        company="Brico",
        classification=EmailClassification.ASSESSMENT,
        offset_days=2,
    )

    detected = await processes.list_detected_processes(session, user_id=user.id)
    assert len(detected) == 2
    by_company = {p.company.lower(): p for p in detected}
    assert by_company["ripple"].message_count == 2
    assert by_company["ripple"].status == ApplicationStatus.ONSITE_LOOP
    assert by_company["ripple"].role == "Senior Software Engineer"
    assert by_company["brico"].status == ApplicationStatus.RECRUITER_SCREEN


async def test_linked_and_dismissed_messages_excluded(session, user):
    from models import Application
    from models.enums import ApplicationStatus, EmailClassification
    from services.email import processes

    application = Application(
        user_id=user.id,
        company="Chime",
        role="SWE",
        status=ApplicationStatus.APPLIED,
    )
    session.add(application)
    await session.flush()

    linked = await _seed_signal(
        session,
        user_id=user.id,
        company="Chime",
        classification=EmailClassification.INTERVIEW_REQUEST,
        offset_days=1,
    )
    linked.application_id = application.id
    session.add(linked)

    dismissed = await _seed_signal(
        session,
        user_id=user.id,
        company="Scribd",
        classification=EmailClassification.INTERVIEW_REQUEST,
        offset_days=2,
    )
    dismissed.process_dismissed_at = datetime.now(UTC)
    session.add(dismissed)
    await session.flush()

    detected = await processes.list_detected_processes(session, user_id=user.id)
    assert detected == []


async def test_track_process_creates_application_at_inferred_stage(session, user):
    from models import Job
    from models.enums import (
        ApplicationBoard,
        ApplicationStatus,
        EmailClassification,
        JobQueueState,
        JobSource,
    )
    from services.email import processes

    # Library already knows the job — track must reuse it, not duplicate.
    job = Job(
        user_id=user.id,
        source=JobSource.LINKEDIN,
        board=ApplicationBoard.GREENHOUSE,
        external_id="x-1",
        url="https://boards.greenhouse.io/ripple/jobs/1",
        url_type="ats",
        company="Ripple",
        role="Senior Software Engineer, Payments",
        description="…",
        queue_state=JobQueueState.UNSWIPED,
        found_at=datetime.now(UTC),
    )
    session.add(job)
    await session.flush()

    first = await _seed_signal(
        session,
        user_id=user.id,
        company="Ripple",
        classification=EmailClassification.INTERVIEW_REQUEST,
        stage="screen",
        offset_days=5,
    )
    await _seed_signal(
        session,
        user_id=user.id,
        company="Ripple",
        classification=EmailClassification.INTERVIEW_REQUEST,
        stage="interview",
        role="Senior Software Engineer",
        offset_days=1,
    )

    application = await processes.track_process(session, user_id=user.id, company="Ripple")
    await session.commit()

    assert application is not None
    assert application.job_id == job.id
    assert application.status == ApplicationStatus.ONSITE_LOOP
    assert application.applied_at == first.received_at

    # Messages + threads linked; the group disappears from detection.
    from sqlmodel import select

    from models import EmailMessage

    msgs = (await session.exec(select(EmailMessage))).all()
    assert all(m.application_id == application.id for m in msgs)
    assert await processes.list_detected_processes(session, user_id=user.id) == []

    # Status trail written for the tracking timeline.
    from models import AppEvent
    from models.enums import AppEventKind

    events = (await session.exec(select(AppEvent))).all()
    status_events = [e for e in events if e.kind == AppEventKind.STATUS_CHANGE]
    assert [e.payload["to"] for e in status_events] == [
        ApplicationStatus.APPLIED.value,
        ApplicationStatus.ONSITE_LOOP.value,
    ]


async def test_dismiss_process_stamps_messages(session, user):
    from models.enums import EmailClassification
    from services.email import processes

    await _seed_signal(
        session,
        user_id=user.id,
        company="Scribd",
        classification=EmailClassification.INTERVIEW_REQUEST,
        offset_days=1,
    )
    n = await processes.dismiss_process(session, user_id=user.id, company="Scribd")
    assert n == 1
    assert await processes.list_detected_processes(session, user_id=user.id) == []
