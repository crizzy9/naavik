"""Plan 96a — B3 residual guards on the classify tick.

1. Commit-boundary characterization: a classification committed by the
   tick survives an inference failure (the 2026-07-07 crash loop rolled
   back — and silently re-billed — every LLM call in the tick).
2. Stall alert: a tick that processes 0 rows while untouched mail waits
   pages via log.error + admin notification instead of idling for 37 h.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import UTC, datetime

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
        EmailAccount,
        EmailMessage,
        EmailThread,
        Settings,
        User,
    )

    tables = [
        User.__table__,
        Settings.__table__,
        EmailAccount.__table__,
        EmailThread.__table__,
        EmailMessage.__table__,
    ]
    for table in tables:
        for c in list(table.constraints):
            if isinstance(c, CheckConstraint):
                table.constraints.discard(c)
    return tables


@pytest.fixture
async def maker():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool
    from sqlmodel.ext.asyncio.session import AsyncSession

    from models import User

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        for table in _tables():
            await conn.run_sync(table.create)
    m = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with m() as s:
        s.add(User(id=1, email="u@x.test", password_hash="x", is_active=True))
        await s.commit()
    yield m
    await engine.dispose()


async def _seed_unclassified(maker, *, n: int = 1) -> list[int]:
    from models import EmailMessage, EmailThread
    from models.enums import EmailClassification

    ids: list[int] = []
    async with maker() as s:
        for i in range(n):
            thread = EmailThread(
                user_id=1,
                provider="imap",
                thread_id_external=f"<t-{i}@x.test>",
                subject=f"Interview with Headway {i}",
                classification=EmailClassification.OTHER,
                latest_message_at=datetime(2026, 7, 8, 12, 0, tzinfo=UTC),
            )
            s.add(thread)
            await s.flush()
            msg = EmailMessage(
                user_id=1,
                thread_id=thread.id,
                provider="imap",
                message_id_external=f"<m-{i}@x.test>",
                sender_email="scheduler@headway.co",
                subject=f"Interview with Headway {i}",
                snippet="…",
                received_at=datetime(2026, 7, 8, 12, 0, tzinfo=UTC),
            )
            s.add(msg)
            await s.flush()
            ids.append(msg.id)
        await s.commit()
    return ids


async def test_classification_survives_inference_failure(maker, monkeypatch):
    """The tick commits classifications BEFORE inference runs — an
    inference crash must not roll back classify work (or its ApiUsage)."""
    from scheduler import jobs
    from services.email import classifier, inference

    [msg_id] = await _seed_unclassified(maker)

    async def fake_classify(session, *, limit=100):
        from models import EmailMessage
        from models.enums import EmailClassification

        msg = await session.get(EmailMessage, msg_id)
        msg.classification = EmailClassification.INTERVIEW_REQUEST
        msg.classification_at = datetime.now(UTC)
        session.add(msg)
        return 1

    async def exploding_infer(session, *, limit=100):
        raise RuntimeError("poison receipt")

    monkeypatch.setattr(jobs, "async_session", maker)
    monkeypatch.setattr(classifier, "classify_unprocessed", fake_classify)
    monkeypatch.setattr(inference, "infer_unprocessed", exploding_infer)

    with pytest.raises(RuntimeError, match="poison receipt"):
        await jobs.classify_emails()

    from models import EmailMessage
    from models.enums import EmailClassification

    async with maker() as s:
        msg = await s.get(EmailMessage, msg_id)
        assert msg.classification == EmailClassification.INTERVIEW_REQUEST


async def test_stall_alert_fires_on_zero_rows_with_backlog(maker, monkeypatch, caplog):
    from models import Settings
    from scheduler import jobs
    from services import notify

    await _seed_unclassified(maker, n=3)
    async with maker() as s:
        s.add(Settings(user_id=1))
        await s.commit()

    notified: list[str] = []

    async def fake_notify(*, settings, message, http_client=None):
        notified.append(message)

    monkeypatch.setattr(notify, "notify_admin_error", fake_notify)

    async with maker() as s:
        with caplog.at_level(logging.ERROR, logger="scheduler.jobs"):
            await jobs._alert_on_classify_stall(s)

    assert any("0 rows" in r.message or "stalled" in r.message for r in caplog.records)
    assert len(notified) == 1
    assert "3 messages waiting" in notified[0]


async def test_stall_alert_silent_when_backlog_is_stamped(maker, monkeypatch, caplog):
    """Degraded-but-honest rows (unclassified_reason set) never page —
    NO_PROVIDER_CONFIGURED is a state, not a stall."""
    from models import EmailMessage
    from models.enums import UnclassifiedReason
    from scheduler import jobs
    from services import notify

    ids = await _seed_unclassified(maker, n=2)
    async with maker() as s:
        for mid in ids:
            msg = await s.get(EmailMessage, mid)
            msg.unclassified_reason = UnclassifiedReason.NO_PROVIDER_CONFIGURED
            s.add(msg)
        await s.commit()

    notified: list[str] = []

    async def fake_notify(*, settings, message, http_client=None):
        notified.append(message)

    monkeypatch.setattr(notify, "notify_admin_error", fake_notify)

    async with maker() as s:
        with caplog.at_level(logging.ERROR, logger="scheduler.jobs"):
            await jobs._alert_on_classify_stall(s)

    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert notified == []
