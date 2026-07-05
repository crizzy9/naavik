"""Email → inferred application tracking — item 5 (2026-07).

Covers the deterministic receipt detector, the three inference outcomes
(link-existing / attach-to-library-job / create-job+application), and the
confirm / dismiss seam.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime

import pytest
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles

os.environ.setdefault("NAAVIK_DEBUG", "1")
os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")

sqlite3.register_adapter(list, json.dumps)
sqlite3.register_adapter(dict, json.dumps)

from services.email import inference  # noqa: E402
from services.email.inference import detect_receipt  # noqa: E402


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw):  # type: ignore[misc]
    return "TEXT"


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_type, _compiler, **_kw):  # type: ignore[misc]
    return "TEXT"


# ── Detector ────────────────────────────────────────────────────────────


def test_detect_greenhouse_receipt():
    hit = detect_receipt(
        sender_email="no-reply@greenhouse.io",
        subject="Thank you for applying to Verkada",
        snippet="We have received your application and will review it shortly.",
    )
    assert hit is not None
    assert hit.board.value == "greenhouse"
    assert hit.company == "Verkada"


def test_detect_lever_receipt_with_role():
    hit = detect_receipt(
        sender_email="no-reply@hire.lever.co",
        subject="Thank you for your interest in the Senior Software Engineer role at Plaid",
        snippet="",
    )
    assert hit is not None
    assert hit.board.value == "lever"
    assert hit.company == "Plaid"
    assert hit.role == "Senior Software Engineer"


def test_detect_linkedin_receipt():
    hit = detect_receipt(
        sender_email="jobs-noreply@linkedin.com",
        subject="Your application was sent to Walmart",
        snippet="You applied to Senior Software Engineer at Walmart.",
    )
    assert hit is not None
    assert hit.board.value == "linkedin"
    assert hit.company == "Walmart"
    assert hit.role == "Senior Software Engineer"


def test_detect_generic_receipt_unknown_sender():
    hit = detect_receipt(
        sender_email="talent@acme-robotics.com",
        subject="Application received — thanks for applying to Acme Robotics!",
        snippet="",
    )
    assert hit is not None
    assert hit.board.value == "company_direct"
    assert hit.company == "Acme Robotics"


def test_detect_extracts_posting_url():
    hit = detect_receipt(
        sender_email="no-reply@greenhouse.io",
        subject="Thank you for applying to Stripe",
        snippet="View the posting: https://boards.greenhouse.io/stripe/jobs/12345",
    )
    assert hit is not None
    assert hit.posting_url == "https://boards.greenhouse.io/stripe/jobs/12345"


def test_non_receipts_are_ignored():
    # ATS sender but not a receipt (interview invite) — phrase gate holds.
    assert (
        detect_receipt(
            sender_email="no-reply@greenhouse.io",
            subject="Interview availability for next week",
            snippet="Please pick a slot.",
        )
        is None
    )
    assert (
        detect_receipt(
            sender_email="newsletter@jobs.example.com",
            subject="10 new jobs for you",
            snippet="",
        )
        is None
    )


# ── Service outcomes (sqlite) ───────────────────────────────────────────


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
        EmailAccount.__table__,
        EmailThread.__table__,
        EmailMessage.__table__,
    ]
    for t in tables:
        bad = [
            c
            for c in list(t.constraints)
            if isinstance(c, CheckConstraint) and "char_length" in str(c.sqltext)
        ]
        for c in bad:
            t.constraints.discard(c)
        bad_idx = [i for i in list(t.indexes) if "gin" in (i.name or "").lower()]
        for i in bad_idx:
            t.indexes.discard(i)
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
        s.add(User(id=1, email="u@x.test", password_hash="x", is_active=True))
        await s.flush()
        yield s
    await engine.dispose()


async def _seed_message(session, *, subject: str, sender: str, snippet: str = ""):
    from models import EmailThread
    from models.email_message import EmailMessage
    from models.enums import EmailClassification

    thread = EmailThread(
        user_id=1,
        provider="imap",
        subject=subject,
        thread_id_external=f"tk-{subject[:20]}",
        classification=EmailClassification.OTHER,
        latest_message_at=datetime(2026, 7, 1, 12, 0, tzinfo=UTC),
    )
    session.add(thread)
    await session.flush()
    msg = EmailMessage(
        user_id=1,
        thread_id=thread.id,
        provider="imap",
        message_id_external=f"mid-{subject[:24]}",
        sender_email=sender,
        subject=subject,
        snippet=snippet,
        received_at=datetime(2026, 7, 1, 12, 0, tzinfo=UTC),
    )
    session.add(msg)
    await session.flush()
    return msg, thread


def _make_job(**overrides):
    from models import Job
    from models.enums import ApplicationBoard, JobSource

    base = {
        "user_id": 1,
        "source": JobSource.MANUAL,
        "external_id": f"x-{overrides.get('company', 'c')}",
        "board": ApplicationBoard.MANUAL,
        "url": f"https://example.com/{overrides.get('company', 'c')}",
        "url_type": "manual",
        "company": "Acme",
        "role": "Software Engineer",
        "description": "d",
        "found_at": datetime(2026, 6, 1, tzinfo=UTC),
    }
    base.update(overrides)
    return Job(**base)


async def test_receipt_creates_job_and_proposed_application(session):
    from sqlmodel import select

    from models import Application, Job

    msg, thread = await _seed_message(
        session,
        subject="Thanks for applying to Initech!",
        sender="no-reply@ashbyhq.com",
    )
    created = await inference.infer_from_message(session, msg)
    assert created is not None

    job = (await session.exec(select(Job))).one()
    assert job.source.value == "email"
    assert job.company == "Initech"
    assert job.url.startswith("manual://email/")

    app_row = (await session.exec(select(Application))).one()
    assert app_row.status.value == "APPLIED"
    assert app_row.applied_at == msg.received_at
    assert inference.is_unconfirmed_inferred(app_row)
    # Message + thread linked → future email signals attach.
    assert msg.application_id == app_row.id
    assert thread.application_id == app_row.id
    assert msg.inference_processed_at is not None


async def test_receipt_attaches_to_existing_library_job(session):
    from sqlmodel import select

    from models import Application, Job

    session.add(_make_job(company="Plaid", role="Senior Software Engineer"))
    await session.flush()

    msg, _ = await _seed_message(
        session,
        subject="Thank you for your interest in the Senior Software Engineer role at Plaid",
        sender="no-reply@hire.lever.co",
    )
    created = await inference.infer_from_message(session, msg)
    assert created is not None

    jobs = (await session.exec(select(Job))).all()
    assert len(jobs) == 1  # no duplicate job created
    app_row = (await session.exec(select(Application))).one()
    assert app_row.job_id == jobs[0].id
    assert app_row.company == "Plaid"


async def test_receipt_links_existing_application_without_new_rows(session):
    from sqlmodel import select

    from models import Application
    from models.enums import ApplicationStatus

    job = _make_job(company="Walmart", role="Senior Software Engineer")
    session.add(job)
    await session.flush()
    existing = Application(
        user_id=1,
        job_id=job.id,
        company="Walmart",
        role="Senior Software Engineer",
        status=ApplicationStatus.APPLIED,
        applied_at=datetime(2026, 6, 20, tzinfo=UTC),
    )
    session.add(existing)
    await session.flush()

    msg, thread = await _seed_message(
        session,
        subject="Your application was sent to Walmart",
        sender="jobs-noreply@linkedin.com",
    )
    created = await inference.infer_from_message(session, msg)
    assert created is None  # linked, not created
    assert msg.application_id == existing.id
    assert thread.application_id == existing.id
    apps = (await session.exec(select(Application))).all()
    assert len(apps) == 1


async def test_confirm_and_dismiss_seam(session):
    msg, _ = await _seed_message(
        session,
        subject="Thanks for applying to Initech!",
        sender="no-reply@ashbyhq.com",
    )
    created = await inference.infer_from_message(session, msg)
    assert created is not None

    pending = await inference.list_unconfirmed(session, user_id=1)
    assert [a.id for a in pending] == [created.id]

    assert await inference.confirm(session, user_id=1, application_id=created.id)
    assert not inference.is_unconfirmed_inferred(created)
    assert await inference.list_unconfirmed(session, user_id=1) == []
    # Double-confirm is a no-op 404 for the route.
    assert not await inference.confirm(session, user_id=1, application_id=created.id)


async def test_dismiss_soft_deletes_but_keeps_job(session):
    from sqlmodel import select

    from models import Application, Job

    msg, _ = await _seed_message(
        session,
        subject="Thanks for applying to Initech!",
        sender="no-reply@ashbyhq.com",
    )
    created = await inference.infer_from_message(session, msg)
    assert await inference.dismiss(session, user_id=1, application_id=created.id)
    app_row = (await session.exec(select(Application))).one()
    assert app_row.deleted_at is not None
    job = (await session.exec(select(Job))).one()
    assert job.deleted_at is None


async def test_infer_unprocessed_skips_non_receipts(session):
    from sqlmodel import select

    from models.email_message import EmailMessage

    await _seed_message(session, subject="Weekly job digest", sender="digest@linkedin.com")
    created = await inference.infer_unprocessed(session)
    assert created == 0
    msg = (await session.exec(select(EmailMessage))).one()
    assert msg.inference_processed_at is not None  # examined exactly once
