"""apply_email_suggestion / dismiss_email_suggestion service tests.

Plan 90 / 0.5.0.03 Wave 9. Service-layer happy path + IDOR + double-resolve
guard. Routes themselves are covered indirectly via the service path; the
key invariant the reviewer cares about is "no destructive flip without
explicit user consent on the right Application".
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles

os.environ.setdefault("NAAVIK_DEBUG", "1")

# This test creates its own in-memory sqlite session — do NOT activate the
# sample-data shim that monkeypatches application_service.update_status.


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw):  # type: ignore[misc]
    return "TEXT"


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_type, _compiler, **_kw):  # type: ignore[misc]
    return "TEXT"


def _email_test_tables():
    from sqlalchemy import CheckConstraint

    from models import (
        AppEvent,
        Application,
        EmailAccount,
        EmailMessage,
        EmailThread,
        User,
    )

    tables = [
        User.__table__,
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
        for idx in list(table.indexes):
            if any(getattr(o, "name", None) == "deleted_at" for o in idx.columns):
                table.indexes.discard(idx)
    return tables


@pytest.fixture
async def session():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool
    from sqlmodel.ext.asyncio.session import AsyncSession

    tables = _email_test_tables()
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


async def _seed(session, *, user_id: int, status):
    from models import Application, EmailMessage, EmailThread, User
    from models.enums import (
        ApplicationStatus,
        DocsState,
        EmailClassification,
        RecruiterState,
        ReferralState,
    )

    user = User(id=user_id, email=f"u{user_id}@x.test", password_hash="x", is_active=True)
    session.add(user)
    await session.flush()

    application = Application(
        user_id=user_id,
        job_id=None,
        company="Acme",
        role="SWE",
        status=status,
        docs_state=DocsState.NONE,
        referral_state=ReferralState.NONE,
        recruiter_state=RecruiterState.NONE,
        applied_at=datetime.now(UTC),
    )
    session.add(application)
    await session.flush()

    thread = EmailThread(
        user_id=user_id,
        provider="imap",
        thread_id_external=f"<t-{user_id}@example.com>",
        subject="Interview request",
        classification=EmailClassification.INTERVIEW_REQUEST,
        latest_message_at=datetime.now(UTC),
    )
    session.add(thread)
    await session.flush()

    msg = EmailMessage(
        user_id=user_id,
        thread_id=thread.id,
        application_id=application.id,
        provider="imap",
        message_id_external=f"<m-{user_id}@example.com>",
        sender_email="rec@example.com",
        subject="Interview request",
        snippet="schedule a chat",
        received_at=datetime.now(UTC),
        classification=EmailClassification.INTERVIEW_REQUEST,
        suggested_status=ApplicationStatus.RECRUITER_SCREEN,
        suggested_at=datetime.now(UTC),
    )
    session.add(msg)
    await session.flush()
    return application, msg


async def test_apply_flips_status_with_auto_from_email_trigger(session):
    from sqlmodel import select

    from models import AppEvent
    from models.enums import ApplicationStatus, StatusChangeTrigger
    from services import applications as application_service

    app, msg = await _seed(session, user_id=42, status=ApplicationStatus.APPLIED)
    updated = await application_service.apply_email_suggestion(
        session,
        application_id=app.id,
        message_id=msg.id,
        user_id=42,
    )
    assert updated.status == ApplicationStatus.RECRUITER_SCREEN
    assert msg.suggestion_applied_at is not None

    events = (await session.exec(select(AppEvent).order_by(AppEvent.id))).all()
    # status change AppEvent payload trigger is AUTO_FROM_EMAIL.
    status_events = [e for e in events if e.kind.value == "status_change"]
    assert any(
        e.payload.get("trigger") == StatusChangeTrigger.AUTO_FROM_EMAIL.value for e in status_events
    )


async def test_apply_idor_rejects_cross_user(session):
    from models.enums import ApplicationStatus
    from services import applications as application_service

    app, msg = await _seed(session, user_id=99, status=ApplicationStatus.APPLIED)
    with pytest.raises(application_service.ApplicationServiceError):
        await application_service.apply_email_suggestion(
            session,
            application_id=app.id,
            message_id=msg.id,
            user_id=42,
        )


async def test_apply_rejects_when_already_applied(session):
    from models.enums import ApplicationStatus
    from services import applications as application_service

    app, msg = await _seed(session, user_id=42, status=ApplicationStatus.APPLIED)
    msg.suggestion_applied_at = datetime.now(UTC)
    session.add(msg)
    await session.flush()
    with pytest.raises(application_service.ValidationError):
        await application_service.apply_email_suggestion(
            session,
            application_id=app.id,
            message_id=msg.id,
            user_id=42,
        )


async def test_dismiss_records_timestamp(session):
    from models.enums import ApplicationStatus
    from services import applications as application_service

    app, msg = await _seed(session, user_id=42, status=ApplicationStatus.APPLIED)
    await application_service.dismiss_email_suggestion(
        session,
        application_id=app.id,
        message_id=msg.id,
        user_id=42,
    )
    assert msg.suggestion_dismissed_at is not None
