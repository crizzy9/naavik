"""EmailAccount + EmailMessage model round-trip + Read schema strip.

Plan 90 / 0.5.0.01 Wave 9. In-memory aiosqlite session so the test runs
without `NAAVIK_LIVE_DB=1`.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles

os.environ.setdefault("NAAVIK_DEBUG", "1")


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw):  # type: ignore[misc]
    return "TEXT"


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_type, _compiler, **_kw):  # type: ignore[misc]
    return "TEXT"


def _email_test_tables():
    """Models we need on the in-memory sqlite for these tests.

    CheckConstraints stripped — they use Postgres `char_length()`.
    """
    from sqlalchemy import CheckConstraint

    from models import (
        Application,
        EmailAccount,
        EmailMessage,
        EmailThread,
        User,
    )

    tables = [
        User.__table__,
        Application.__table__,
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


async def test_email_account_round_trip(session):
    from models import EmailAccount, User
    from models.enums import EmailAccountProvider, EmailAccountStatus

    user = User(email="owner@example.com", password_hash="x", is_active=True)
    session.add(user)
    await session.flush()

    account = EmailAccount(
        user_id=user.id,
        provider=EmailAccountProvider.IMAP,
        account_email="owner@example.com",
        imap_host="imap.example.com",
        imap_username="owner@example.com",
        imap_password="plaintext-secret",
    )
    session.add(account)
    await session.flush()
    await session.commit()

    from sqlmodel import select

    rows = (await session.exec(select(EmailAccount))).all()
    assert len(rows) == 1
    assert rows[0].status == EmailAccountStatus.OK
    assert rows[0].imap_port == 993
    assert rows[0].imap_use_tls is True


async def test_email_account_read_schema_strips_password(session):
    """`EmailAccountRead` (the API surface) must NEVER expose imap_password."""
    from api.integrations_email import EmailAccountRead
    from models import EmailAccount, User
    from models.enums import EmailAccountProvider

    user = User(email="reader@example.com", password_hash="x", is_active=True)
    session.add(user)
    await session.flush()

    account = EmailAccount(
        user_id=user.id,
        provider=EmailAccountProvider.IMAP,
        account_email="reader@example.com",
        imap_host="imap.example.com",
        imap_username="reader@example.com",
        imap_password="leak-me-if-you-can",
    )
    session.add(account)
    await session.flush()

    payload = EmailAccountRead.model_validate(account).model_dump()
    flat = " ".join(str(v) for v in payload.values())
    assert "leak-me-if-you-can" not in flat
    assert "imap_password" not in payload
    assert payload["account_email"] == "reader@example.com"


async def test_email_message_creation(session):
    from models import EmailAccount, EmailMessage, EmailThread, User
    from models.enums import EmailAccountProvider, EmailClassification

    user = User(email="msg@example.com", password_hash="x", is_active=True)
    session.add(user)
    await session.flush()

    thread = EmailThread(
        user_id=user.id,
        provider="imap",
        thread_id_external="<thread-1@example.com>",
        subject="Interview request",
        classification=EmailClassification.OTHER,
        latest_message_at=datetime.now(UTC),
    )
    session.add(thread)
    await session.flush()

    account = EmailAccount(
        user_id=user.id,
        provider=EmailAccountProvider.IMAP,
        account_email="msg@example.com",
        imap_host="imap.example.com",
        imap_username="msg@example.com",
        imap_password="x",
    )
    session.add(account)
    await session.flush()

    snippet_text = "Hello, would love to schedule a chat next week."
    msg = EmailMessage(
        user_id=user.id,
        thread_id=thread.id,
        account_id=account.id,
        provider="imap",
        message_id_external="<msg-1@example.com>",
        sender_email="recruiter@example.com",
        sender_name="Recruiter Rita",
        subject="Interview request",
        snippet=snippet_text,
        received_at=datetime.now(UTC),
    )
    session.add(msg)
    await session.flush()

    from sqlmodel import select

    rows = (await session.exec(select(EmailMessage))).all()
    assert len(rows) == 1
    assert rows[0].snippet == snippet_text
    assert rows[0].classification is None
    assert rows[0].auto_classified is True
