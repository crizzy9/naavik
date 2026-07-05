"""email_classifier — no-LLM graceful degrade + happy path.

Plan 90 / 0.5.0.02 Wave 9. The owner has NO LLM connected; this test pins
the degrade behavior so the rest of the flow (sync → persist) keeps working
without an LLM.
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


async def _seed_message(session, *, user_id: int, app_id: int | None = None):
    from models import EmailMessage, EmailThread
    from models.enums import EmailClassification

    thread = EmailThread(
        user_id=user_id,
        provider="imap",
        thread_id_external="<t-1@example.com>",
        subject="Interview request",
        classification=EmailClassification.OTHER,
        latest_message_at=datetime.now(UTC),
    )
    session.add(thread)
    await session.flush()

    msg = EmailMessage(
        user_id=user_id,
        thread_id=thread.id,
        application_id=app_id,
        provider="imap",
        message_id_external="<m-1@example.com>",
        sender_email="rec@example.com",
        sender_name="Recruiter",
        subject="Interview request",
        snippet="Would love to schedule a chat next week.",
        received_at=datetime.now(UTC),
    )
    session.add(msg)
    await session.flush()
    return msg


async def test_classifier_no_settings_marks_no_provider(session, monkeypatch):
    """No Settings row → no LLM provider → graceful degrade."""
    from models import UnclassifiedReason, User
    from services.email import classifier as email_classifier

    user = User(email="noprov@example.com", password_hash="x", is_active=True)
    session.add(user)
    await session.flush()
    msg = await _seed_message(session, user_id=user.id)

    async def _no_settings(_session, *, user_id):
        return None

    monkeypatch.setattr(email_classifier, "_get_settings", _no_settings)
    processed = await email_classifier.classify_unprocessed(session)
    await session.commit()

    assert processed == 0
    assert msg.classification is None
    assert msg.unclassified_reason == UnclassifiedReason.NO_PROVIDER_CONFIGURED


async def test_classifier_auth_required_marks_no_provider(session, monkeypatch):
    """Settings present but no env keys → `get_provider` raises auth_required
    → degrade path, same as no Settings."""
    from types import SimpleNamespace

    from llm import LLMProviderError
    from models import UnclassifiedReason, User
    from services.email import classifier as email_classifier

    user = User(email="auth@example.com", password_hash="x", is_active=True)
    session.add(user)
    await session.flush()
    await _seed_message(session, user_id=user.id)

    async def _fake_get_settings(_session, *, user_id):
        return SimpleNamespace(user_id=user_id)

    def _no_provider(_settings):
        raise LLMProviderError("no key", kind="auth_required")

    monkeypatch.setattr(email_classifier, "_get_settings", _fake_get_settings)
    monkeypatch.setattr(email_classifier, "get_provider", _no_provider)
    processed = await email_classifier.classify_unprocessed(session)
    await session.commit()
    assert processed == 0

    from sqlmodel import select

    from models import EmailMessage

    rows = (await session.exec(select(EmailMessage))).all()
    assert rows[0].unclassified_reason == UnclassifiedReason.NO_PROVIDER_CONFIGURED
    assert rows[0].auto_classified is False


async def test_classifier_happy_path(session, monkeypatch):
    """Provider available → tracked_call returns a structured result →
    classification persisted + AppEvent emitted."""
    from types import SimpleNamespace

    from llm.prompts.classify_email import EmailClassificationResult
    from models import User
    from models.enums import EmailClassification
    from services.email import classifier as email_classifier

    user = User(email="happy@example.com", password_hash="x", is_active=True)
    session.add(user)
    await session.flush()
    msg = await _seed_message(session, user_id=user.id)

    class _FakeProvider:
        model = "claude-sonnet-stub"

    class _FakeStructured:
        def __init__(self, value):
            self.value = value

    async def _fake_get_settings(_session, *, user_id):
        return SimpleNamespace(user_id=user_id)

    monkeypatch.setattr(email_classifier, "_get_settings", _fake_get_settings)
    monkeypatch.setattr(email_classifier, "get_provider", lambda _s: _FakeProvider())

    async def _fake_tracked_call(**kwargs):
        return _FakeStructured(
            EmailClassificationResult(classification="interview_request", urgency="high")
        )

    monkeypatch.setattr(email_classifier.llm_tracker, "tracked_call", _fake_tracked_call)

    processed = await email_classifier.classify_unprocessed(session)
    await session.commit()

    assert processed == 1
    assert msg.classification == EmailClassification.INTERVIEW_REQUEST
    assert msg.urgency == "high"
    assert msg.classification_model == "claude-sonnet-stub"


async def test_classifier_caps_subject_and_sender_in_prompt(session, monkeypatch):
    """A pre-existing over-long subject/sender is capped before it reaches the
    classify_email prompt (PR #214 hacker M1 defense-in-depth)."""
    from types import SimpleNamespace

    from llm.prompts.classify_email import EmailClassificationResult
    from models import User
    from services.email import classifier as email_classifier

    user = User(email="cap2@example.com", password_hash="x", is_active=True)
    session.add(user)
    await session.flush()
    msg = await _seed_message(session, user_id=user.id)
    # Simulate a pre-existing row that escaped the persist-time cap.
    msg.subject = "X" * 5000
    msg.sender_email = "a" * 4000 + "@evil.example.com"
    session.add(msg)
    await session.flush()

    captured: dict[str, str] = {}

    class _FakeProvider:
        model = "stub"

    class _FakeStructured:
        def __init__(self, value):
            self.value = value

    async def _fake_get_settings(_session, *, user_id):
        return SimpleNamespace(user_id=user_id)

    async def _fake_tracked_call(**kwargs):
        captured["prompt"] = kwargs["prompt"]
        return _FakeStructured(EmailClassificationResult(classification="other"))

    monkeypatch.setattr(email_classifier, "_get_settings", _fake_get_settings)
    monkeypatch.setattr(email_classifier, "get_provider", lambda _s: _FakeProvider())
    monkeypatch.setattr(email_classifier.llm_tracker, "tracked_call", _fake_tracked_call)

    await email_classifier.classify_unprocessed(session)

    assert "X" * 200 in captured["prompt"]
    assert "X" * 201 not in captured["prompt"]
    assert "a" * 254 in captured["prompt"]
    assert "a" * 255 not in captured["prompt"]


async def test_classifier_llm_failure_marks_llm_failed(session, monkeypatch):
    from types import SimpleNamespace

    from llm import LLMProviderError
    from models import UnclassifiedReason, User
    from services.email import classifier as email_classifier

    user = User(email="fail@example.com", password_hash="x", is_active=True)
    session.add(user)
    await session.flush()
    msg = await _seed_message(session, user_id=user.id)

    class _FakeProvider:
        model = "claude-stub"

    async def _fake_get_settings(_session, *, user_id):
        return SimpleNamespace(user_id=user_id)

    monkeypatch.setattr(email_classifier, "_get_settings", _fake_get_settings)
    monkeypatch.setattr(email_classifier, "get_provider", lambda _s: _FakeProvider())

    async def _boom(**kwargs):
        raise LLMProviderError("rate limited", kind="rate_limit")

    monkeypatch.setattr(email_classifier.llm_tracker, "tracked_call", _boom)

    processed = await email_classifier.classify_unprocessed(session)
    await session.commit()
    assert processed == 0
    assert msg.unclassified_reason == UnclassifiedReason.RATE_LIMITED
