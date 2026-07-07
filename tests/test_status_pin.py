"""Manual-over-email precedence contract — plan 95 § 3.8 (slice 95h).

One test per contract rule: provenance (1), backward-move pin (2), forward
news flows (3), manual CLOSED absolute (4), suppressed transitions still
recorded (5), and the three unpin paths (6).
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime
from types import SimpleNamespace

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

    u = User(email="pin@example.com", password_hash="x", is_active=True)
    session.add(u)
    await session.flush()
    return u


@pytest.fixture
async def application(session, user):
    from models import Application
    from models.enums import ApplicationStatus

    a = Application(
        user_id=user.id,
        company="Chime",
        role="Senior Software Engineer",
        status=ApplicationStatus.APPLIED,
        applied_at=datetime.now(UTC),
    )
    session.add(a)
    await session.flush()
    return a


async def _classify_email(session, monkeypatch, *, application, llm: dict):
    """Run one email through the real classifier dispatch."""
    from models import EmailMessage, EmailThread
    from models.enums import EmailClassification
    from services.email import classifier as email_classifier

    when = datetime.now(UTC)
    thread = EmailThread(
        user_id=application.user_id,
        provider="imap",
        thread_id_external=f"<t-{when.timestamp()}@x>",
        subject="s",
        classification=EmailClassification.OTHER,
        latest_message_at=when,
        application_id=application.id,
    )
    session.add(thread)
    await session.flush()
    msg = EmailMessage(
        user_id=application.user_id,
        thread_id=thread.id,
        application_id=application.id,
        provider="imap",
        message_id_external=f"<m-{when.timestamp()}@x>",
        sender_email="recruiting@chime.com",
        subject="Update from Chime",
        snippet="…",
        received_at=when,
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
        return _FakeStructured(dict(llm))

    async def _no_notify(**kwargs):
        return None

    monkeypatch.setattr(email_classifier, "_get_settings", _fake_get_settings)
    monkeypatch.setattr(email_classifier, "get_provider", lambda _s: _FakeProvider())
    monkeypatch.setattr(email_classifier.llm_tracker, "tracked_call", _fake_tracked_call)
    monkeypatch.setattr(email_classifier.notify, "notify_priority_email", _no_notify)
    await email_classifier.classify_unprocessed(session)
    return msg


_INTERVIEW_LLM = {
    "classification": "interview_request",
    "urgency": "high",
    "company": "Chime",
    "stage": "interview",
    "sender_type": "employer",
}
_OFFER_LLM = {
    "classification": "offer",
    "urgency": "high",
    "company": "Chime",
    "sender_type": "employer",
}


# Rule 1 — provenance: every status write records its trigger.
async def test_rule1_provenance_in_event_payload(session, user, application, monkeypatch):
    from sqlmodel import select

    from models import AppEvent
    from models.enums import AppEventKind, ApplicationStatus
    from services import applications as applications_service

    await _classify_email(session, monkeypatch, application=application, llm=_INTERVIEW_LLM)
    await applications_service.update_status(
        session, application.id, ApplicationStatus.RECRUITER_SCREEN
    )
    events = [
        e
        for e in (await session.exec(select(AppEvent))).all()
        if e.kind == AppEventKind.STATUS_CHANGE
    ]
    assert [e.payload["trigger"] for e in events] == ["auto-from-email", "manual"]


# Rule 2 — a backward manual move pins; email won't re-apply that status.
async def test_rule2_backward_move_pins_against_reapplication(
    session, user, application, monkeypatch
):
    from models.enums import ApplicationStatus
    from services import applications as applications_service

    # Email auto-advances to Interview Stage…
    await _classify_email(session, monkeypatch, application=application, llm=_INTERVIEW_LLM)
    assert application.status == ApplicationStatus.ONSITE_LOOP

    # …owner says "no, still recruiter screen" (backward manual drag).
    await applications_service.update_status(
        session, application.id, ApplicationStatus.RECRUITER_SCREEN
    )
    pin = applications_service.get_status_pin(application)
    assert pin is not None and pin["rejected"] == "ONSITE_LOOP"

    # The same interview email arrives again: suggestion only, no re-apply.
    msg = await _classify_email(session, monkeypatch, application=application, llm=_INTERVIEW_LLM)
    await session.refresh(application)
    assert application.status == ApplicationStatus.RECRUITER_SCREEN
    assert msg.suggested_status == ApplicationStatus.ONSITE_LOOP
    assert msg.suggestion_applied_at is None


# Rule 3 — forward manual moves never block better news.
async def test_rule3_offer_email_still_lands_on_pinned_application(
    session, user, application, monkeypatch
):
    from models.enums import ApplicationStatus
    from services import applications as applications_service

    await _classify_email(session, monkeypatch, application=application, llm=_INTERVIEW_LLM)
    await applications_service.update_status(
        session, application.id, ApplicationStatus.RECRUITER_SCREEN
    )  # pins ONSITE_LOOP

    # An OFFER email is strictly forward and uncontradicted — it flows.
    await _classify_email(session, monkeypatch, application=application, llm=_OFFER_LLM)
    await session.refresh(application)
    assert application.status == ApplicationStatus.OFFER


# Rule 4 — CLOSED set manually is absolute: suggestions only, forever.
async def test_rule4_manual_closed_is_absolute(session, user, application, monkeypatch):
    from models.enums import ApplicationStatus, ClosedReason
    from services import applications as applications_service

    await applications_service.update_status(
        session,
        application.id,
        ApplicationStatus.CLOSED,
        closed_reason=ClosedReason.WITHDRAWN_BY_ME,
    )
    msg = await _classify_email(session, monkeypatch, application=application, llm=_OFFER_LLM)
    await session.refresh(application)
    assert application.status == ApplicationStatus.CLOSED  # untouched
    assert msg.suggested_status == ApplicationStatus.OFFER  # surfaced, not applied
    assert msg.suggestion_applied_at is None


# Rule 5 — suppressed transitions still emit EMAIL_STATUS_SUGGESTED.
async def test_rule5_suppressed_transition_recorded(session, user, application, monkeypatch):
    from sqlmodel import select

    from models import AppEvent
    from models.enums import AppEventKind, ApplicationStatus
    from services import applications as applications_service

    await _classify_email(session, monkeypatch, application=application, llm=_INTERVIEW_LLM)
    await applications_service.update_status(
        session, application.id, ApplicationStatus.RECRUITER_SCREEN
    )
    await _classify_email(session, monkeypatch, application=application, llm=_INTERVIEW_LLM)

    suggested = [
        e
        for e in (await session.exec(select(AppEvent))).all()
        if e.kind == AppEventKind.EMAIL_STATUS_SUGGESTED
    ]
    assert suggested, "suppressed transition must still be recorded"
    last = suggested[-1]
    assert last.payload["applied"] is False
    assert last.payload["suppressed_by_pin"] is True


# Rule 6a — explicit unpin resumes auto-tracking.
async def test_rule6a_clear_pin_resumes_auto(session, user, application, monkeypatch):
    from models.enums import ApplicationStatus
    from services import applications as applications_service

    await _classify_email(session, monkeypatch, application=application, llm=_INTERVIEW_LLM)
    await applications_service.update_status(
        session, application.id, ApplicationStatus.RECRUITER_SCREEN
    )
    await applications_service.clear_pin(session, user_id=user.id, application_id=application.id)
    await _classify_email(session, monkeypatch, application=application, llm=_INTERVIEW_LLM)
    await session.refresh(application)
    assert application.status == ApplicationStatus.ONSITE_LOOP  # auto resumed


# Rule 6c — the pin auto-clears when the human advances to/past it.
async def test_rule6c_pin_clears_when_human_advances_past(session, user, application, monkeypatch):
    from models.enums import ApplicationStatus
    from services import applications as applications_service

    await _classify_email(session, monkeypatch, application=application, llm=_INTERVIEW_LLM)
    await applications_service.update_status(
        session, application.id, ApplicationStatus.RECRUITER_SCREEN
    )  # pins ONSITE_LOOP
    assert applications_service.get_status_pin(application) is not None

    await applications_service.update_status(
        session, application.id, ApplicationStatus.ONSITE_LOOP
    )  # human themselves advance to the pinned status
    assert applications_service.get_status_pin(application) is None


# Rule 6b — "Apply & resume": accepting the suggestion clears the pin (route
# semantics exercised at the service level: apply + clear_pin together).
async def test_rule6b_apply_and_resume(session, user, application, monkeypatch):
    from models.enums import ApplicationStatus
    from services import applications as applications_service

    await _classify_email(session, monkeypatch, application=application, llm=_INTERVIEW_LLM)
    await applications_service.update_status(
        session, application.id, ApplicationStatus.RECRUITER_SCREEN
    )
    msg = await _classify_email(session, monkeypatch, application=application, llm=_INTERVIEW_LLM)
    assert msg.suggestion_applied_at is None  # suppressed by pin

    await applications_service.apply_email_suggestion(
        session, application_id=application.id, message_id=msg.id, user_id=user.id
    )
    await applications_service.clear_pin(session, user_id=user.id, application_id=application.id)
    await session.refresh(application)
    assert application.status == ApplicationStatus.ONSITE_LOOP
    assert applications_service.get_status_pin(application) is None
