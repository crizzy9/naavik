"""Plan 96c1 — thread job-link + the one-call job-surface ctx.

Aggregation contract: every entity class about a job is reachable from one
`build_job_surface_ctx` call — multi-application jobs, mail-without-
application jobs (96c1 thread job link), job-less manual applications.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

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


# ── Migration 0046 chain + model shape ───────────────────────────────────

_MIG = (
    Path(__file__).resolve().parent.parent
    / "migrations"
    / "versions"
    / "0046_email_thread_job_link.py"
)


def test_0046_chains_from_0045():
    spec = importlib.util.spec_from_file_location("_alembic_0046", _MIG)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "0046_email_thread_job_link"
    assert module.down_revision == "0045_full_body_optin"


def test_email_thread_model_declares_job_id():
    from models import EmailThread

    col = EmailThread.__table__.c.job_id
    assert col.nullable


# ── Fixtures ─────────────────────────────────────────────────────────────


def _tables():
    from sqlalchemy import CheckConstraint

    from models import (
        AppEvent,
        Application,
        ApplicationScreenerAnswer,
        CompanyAlias,
        Contact,
        EmailAccount,
        EmailMessage,
        EmailThread,
        GeneratedDocument,
        Job,
        SenderRule,
        User,
    )
    from models.calendar_event import CalendarConnection, CalendarEvent
    from models.contact import ContactApplicationLink
    from models.interview_round import InterviewRound

    tables = [
        User.__table__,
        Job.__table__,
        Application.__table__,
        AppEvent.__table__,
        EmailAccount.__table__,
        EmailThread.__table__,
        EmailMessage.__table__,
        CompanyAlias.__table__,
        Contact.__table__,
        ContactApplicationLink.__table__,
        SenderRule.__table__,
        GeneratedDocument.__table__,
        ApplicationScreenerAnswer.__table__,
        InterviewRound.__table__,
        CalendarConnection.__table__,
        CalendarEvent.__table__,
    ]
    for table in tables:
        for c in list(table.constraints):
            if isinstance(c, CheckConstraint):
                table.constraints.discard(c)
        bad_idx = [
            i
            for i in list(table.indexes)
            if "gin" in (i.name or "").lower()
            # Partial on Postgres (WHERE deleted_at IS NULL); sqlite would
            # enforce it unconditionally and block soft-deleted history.
            or "alive_unique" in (i.name or "")
        ]
        for i in bad_idx:
            table.indexes.discard(i)
    return tables


@pytest.fixture
async def session():
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
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        s.add(User(id=1, email="surface@x.test", password_hash="x", is_active=True))
        s.add(User(id=2, email="intruder@x.test", password_hash="x", is_active=True))
        await s.flush()
        yield s
    await engine.dispose()


def _job(**overrides):
    from models import Job
    from models.enums import ApplicationBoard, JobSource

    base = {
        "user_id": 1,
        "source": JobSource.MANUAL,
        "external_id": f"js-{overrides.get('company', 'c')}",
        "board": ApplicationBoard.MANUAL,
        "url": "https://example.com/x",
        "url_type": "manual",
        "company": "Acme",
        "role": "Engineer",
        "description": "JD text",
        "found_at": datetime(2026, 6, 1, tzinfo=UTC),
    }
    base.update(overrides)
    return Job(**base)


def _application(job_id=None, **overrides):
    from models import Application
    from models.enums import ApplicationStatus

    base = {
        "user_id": 1,
        "job_id": job_id,
        "company": "Acme",
        "role": "Engineer",
        "status": ApplicationStatus.APPLIED,
        "applied_at": datetime(2026, 6, 10, tzinfo=UTC),
    }
    base.update(overrides)
    return Application(**base)


async def _thread(session, *, user_id=1, subject="t", application_id=None, job_id=None):
    from models import EmailThread
    from models.enums import EmailClassification

    t = EmailThread(
        user_id=user_id,
        provider="imap",
        thread_id_external=f"<{subject}@x>",
        subject=subject,
        classification=EmailClassification.INTERVIEW_REQUEST,
        latest_message_at=datetime(2026, 7, 1, tzinfo=UTC),
        application_id=application_id,
        job_id=job_id,
        message_count=1,
    )
    session.add(t)
    await session.flush()
    return t


async def _build(session, **kw):
    from ui.job_surface_ctx import build_job_surface_ctx

    return await build_job_surface_ctx(session, user_id=kw.pop("user_id", 1), **kw)


# ── link_thread writes both facts ────────────────────────────────────────


async def test_link_thread_denormalizes_job_id(session):
    from services.email.service import link_thread, unlink_thread_links

    job = _job()
    session.add(job)
    await session.flush()
    app = _application(job_id=job.id)
    session.add(app)
    await session.flush()
    t = await _thread(session)

    link_thread(t, app)
    assert t.application_id == app.id
    assert t.job_id == job.id

    unlink_thread_links(t)
    assert t.application_id is None
    assert t.job_id is None


async def test_track_process_sets_thread_job_id(session):
    """The 96c1 invariant at a real link site: Track-it links threads to the
    application AND its job."""
    from models import EmailMessage, EmailThread
    from models.enums import EmailClassification
    from services.email import processes

    t = await _thread(session, subject="Interview with NewCo")
    session.add(
        EmailMessage(
            user_id=1,
            thread_id=t.id,
            provider="imap",
            message_id_external="<nc-1@x>",
            sender_email="talent@newco.com",
            subject="Interview with NewCo",
            snippet="…",
            received_at=datetime(2026, 7, 1, tzinfo=UTC),
            classification=EmailClassification.INTERVIEW_REQUEST,
            extracted_company="NewCo",
        )
    )
    await session.flush()
    application = await processes.track_process(session, user_id=1, company="NewCo")
    assert application is not None
    assert application.job_id is not None
    refreshed = await session.get(EmailThread, t.id)
    assert refreshed.application_id == application.id
    assert refreshed.job_id == application.job_id


# ── ctx aggregation ──────────────────────────────────────────────────────


async def test_multi_application_job_all_surface_newest_primary(session):
    from models.enums import ApplicationStatus

    job = _job()
    session.add(job)
    await session.flush()
    older = _application(
        job_id=job.id,
        status=ApplicationStatus.CLOSED,
        created_at=datetime(2026, 5, 1, tzinfo=UTC),
        deleted_at=datetime(2026, 5, 20, tzinfo=UTC),
    )
    newer = _application(
        job_id=job.id,
        status=ApplicationStatus.RECRUITER_SCREEN,
        created_at=datetime(2026, 6, 20, tzinfo=UTC),
    )
    session.add(older)
    session.add(newer)
    await session.flush()

    ctx = await _build(session, job_id=job.id)
    assert ctx is not None
    apps = ctx["surface_applications"]
    assert len(apps) == 2
    assert apps[0]["id"] == newer.id and apps[0]["is_selected"]
    assert apps[1]["id"] == older.id and apps[1]["is_removed"]
    assert ctx["surface"]["view"] == "post_apply"
    assert ctx["surface"]["application_id"] == newer.id

    # Selecting the older application flips the detail to it.
    ctx = await _build(session, job_id=job.id, application_id=older.id)
    assert ctx["surface"]["application_id"] == older.id
    assert ctx["surface"]["closed"] is not None


async def test_job_with_mail_but_no_application_is_pre_apply(session):
    job = _job(company="MailOnly")
    session.add(job)
    await session.flush()
    await _thread(session, subject="Re: MailOnly intro", job_id=job.id)

    ctx = await _build(session, job_id=job.id)
    assert ctx is not None
    assert ctx["surface"]["view"] == "pre_apply"
    assert ctx["application"] is None
    assert [t["subject"] for t in ctx["unlinked_job_threads"]] == ["Re: MailOnly intro"]


async def test_jobless_manual_application_builds_from_application(session):
    app = _application(job_id=None, company="NoJob Co")
    session.add(app)
    await session.flush()

    ctx = await _build(session, application_id=app.id)
    assert ctx is not None
    assert ctx["job"] is None
    assert ctx["surface"]["view"] == "post_apply"
    assert ctx["surface"]["can_pre"] is False
    assert ctx["surface"]["page_url"] is None
    assert ctx["surface"]["company"] == "NoJob Co"


async def test_draft_application_derives_pre_apply_with_manual_override(session):
    from models.enums import ApplicationStatus

    job = _job()
    session.add(job)
    await session.flush()
    draft = _application(job_id=job.id, status=ApplicationStatus.DRAFT)
    session.add(draft)
    await session.flush()

    ctx = await _build(session, job_id=job.id)
    assert ctx["surface"]["view"] == "pre_apply"
    ctx = await _build(session, job_id=job.id, view_override="post_apply")
    assert ctx["surface"]["view"] == "post_apply"


async def test_cross_user_and_mismatched_ids_return_none(session):
    job = _job()
    session.add(job)
    await session.flush()
    app = _application(job_id=job.id)
    session.add(app)
    other_job = _job(company="Other", external_id="js-other", url="https://example.com/other")
    session.add(other_job)
    await session.flush()

    assert await _build(session, job_id=job.id, user_id=2) is None
    assert await _build(session, application_id=app.id, user_id=2) is None
    # application must belong to the job when both are passed
    assert await _build(session, job_id=other_job.id, application_id=app.id) is None
    assert await _build(session, job_id=99999) is None
