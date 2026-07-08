"""Conversation section on the job surface — plan 95 § 3.9, migrated in 96c3.

The evidence surface: threads + snippets that produced the status, inline
suggestion state, and the § 3.4 reclassify/unlink mounts.
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
        Application,
        CompanyAlias,
        EmailAccount,
        EmailMessage,
        EmailThread,
        SenderRule,
        User,
    )

    tables = [
        User.__table__,
        Application.__table__,
        EmailThread.__table__,
        EmailAccount.__table__,
        EmailMessage.__table__,
        CompanyAlias.__table__,
        SenderRule.__table__,
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

    u = User(email="conv@example.com", password_hash="x", is_active=True)
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
        status=ApplicationStatus.ONSITE_LOOP,
    )
    session.add(a)
    await session.flush()
    return a


async def _seed_thread_with_messages(session, *, user_id: int, application_id: int):
    from models import EmailMessage, EmailThread
    from models.enums import ApplicationStatus, EmailClassification

    now = datetime.now(UTC)
    thread = EmailThread(
        user_id=user_id,
        provider="imap",
        thread_id_external="<t-conv@x>",
        subject="Your system design round at Camber",
        classification=EmailClassification.INTERVIEW_REQUEST,
        latest_message_at=now,
        application_id=application_id,
    )
    session.add(thread)
    await session.flush()
    applied = EmailMessage(
        user_id=user_id,
        thread_id=thread.id,
        application_id=application_id,
        provider="imap",
        message_id_external="<m-conv-1@x>",
        sender_email="recruiting@camber.health",
        sender_name="Camber Recruiting",
        subject="Your system design round at Camber",
        snippet="We'd like to schedule your system design round.",
        received_at=now - timedelta(days=2),
        classification=EmailClassification.INTERVIEW_REQUEST,
        suggested_status=ApplicationStatus.ONSITE_LOOP,
        suggestion_applied_at=now - timedelta(days=2),
    )
    pending = EmailMessage(
        user_id=user_id,
        thread_id=thread.id,
        application_id=application_id,
        provider="imap",
        message_id_external="<m-conv-2@x>",
        sender_email="recruiting@camber.health",
        sender_name="Camber Recruiting",
        subject="Re: Your system design round at Camber",
        snippet="Unfortunately we have decided to move forward with other candidates.",
        received_at=now,
        classification=EmailClassification.REJECTION,
        suggested_status=ApplicationStatus.CLOSED,
    )
    session.add(applied)
    session.add(pending)
    await session.flush()
    return thread, applied, pending


async def test_conversation_ctx_shapes_threads_and_suggestions(session, user, application):
    from ui import tracking_ctx as tctx

    thread, applied, pending = await _seed_thread_with_messages(
        session, user_id=user.id, application_id=application.id
    )
    threads = await tctx.build_conversation_ctx(session, application)
    assert len(threads) == 1
    t = threads[0]
    assert t["subject"] == "Your system design round at Camber"
    assert t["message_count"] == 2
    msgs = {m["id"]: m for m in t["messages"]}
    assert msgs[applied.id]["suggestion"]["applied"] is True
    assert msgs[pending.id]["suggestion"]["pending"] is True
    assert msgs[pending.id]["suggestion"]["status_label"]  # human label present
    assert msgs[pending.id]["provider_link"].endswith("m-conv-2@x")


async def test_conversation_section_template_renders(session, user, application):
    """Template-level: threads listed, Apply/Dismiss present for the pending
    suggestion, applied chip for the auto one, reclassify + unlink mounts."""
    from ui import tracking_ctx as tctx
    from ui.templates_setup import templates

    thread, applied, pending = await _seed_thread_with_messages(
        session, user_id=user.id, application_id=application.id
    )
    conversation = await tctx.build_conversation_ctx(session, application)
    template = templates.env.get_template("components/jobs/_surface_conversation.html")
    html = template.render(
        application={"id": application.id, "company": application.company},
        conversation_threads=conversation,
        unlinked_job_threads=[],
        status_pin={"rejected_label": "Interview Stage"},
        csrf_token="tok",
    )
    assert f'data-testid="conversation-thread-{thread.id}"' in html
    assert f'data-testid="suggestion-apply-{pending.id}"' in html
    assert f'data-testid="suggestion-apply-resume-{pending.id}"' in html  # pinned
    assert f'data-testid="suggestion-dismiss-{pending.id}"' in html
    assert f'data-testid="reclassify-{pending.id}-rejection"' in html
    assert f'data-testid="conversation-unlink-{thread.id}"' in html
    assert "auto-applied" in html  # 96b signal-detail outcome chip


async def test_conversation_section_empty_state(session, user, application):
    from ui import tracking_ctx as tctx
    from ui.templates_setup import templates

    conversation = await tctx.build_conversation_ctx(session, application)
    template = templates.env.get_template("components/jobs/_surface_conversation.html")
    html = template.render(
        application={"id": application.id, "company": application.company},
        conversation_threads=conversation,
        unlinked_job_threads=[],
        status_pin=None,
        csrf_token="tok",
    )
    assert "No linked email yet" in html


@pytest.mark.uses_sample_data_shims
def test_slide_over_fragment_contains_conversation_section():
    """The detail fragment mounts the section (empty state under shims) and
    stays a fragment — no page shell (granularity guard)."""
    import asyncio

    from fastapi.testclient import TestClient

    from db import sample_data as sd
    from main import app

    async def _find():
        apps = await sd.applications_visible_in_tracking()
        return apps[0].id if apps else None

    app_id = asyncio.run(_find())
    assert app_id is not None
    client = TestClient(app, raise_server_exceptions=True)
    client.cookies.set("naavik_session", "fake-1")
    r = client.get(f"/_fragments/tracking/application/{app_id}")
    assert r.status_code == 200
    assert 'data-testid="surface-conversation"' in r.text
    assert "<html" not in r.text.lower()  # fragment granularity holds
