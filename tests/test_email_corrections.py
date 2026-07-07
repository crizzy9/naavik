"""Correction loop — plan 95 § 3.4 (slice 95b).

Reclassify / unlink / merge affordances: the fix sticks (state changes ride
the existing dispatch), and the fix is RECORDED (`ClassificationCorrection`
rows — the labeled dataset the few-shot block and eval harness consume).
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
        ClassificationCorrection,
        CompanyAlias,
        EmailAccount,
        EmailMessage,
        EmailThread,
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
        ClassificationCorrection.__table__,
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

    u = User(email="corr@example.com", password_hash="x", is_active=True)
    session.add(u)
    await session.flush()
    return u


async def _seed_message(
    session,
    *,
    user_id: int,
    company: str | None,
    classification,
    subject: str = "About your interview",
    snippet: str = "…",
    application_id: int | None = None,
    offset_days: int = 0,
):
    from models import EmailMessage, EmailThread
    from models.enums import EmailClassification

    when = datetime.now(UTC) - timedelta(days=offset_days)
    thread = EmailThread(
        user_id=user_id,
        provider="imap",
        thread_id_external=f"<t-{company}-{offset_days}-{subject[:12]}@x>",
        subject=subject,
        classification=EmailClassification.OTHER,
        latest_message_at=when,
        application_id=application_id,
    )
    session.add(thread)
    await session.flush()
    msg = EmailMessage(
        user_id=user_id,
        thread_id=thread.id,
        provider="imap",
        message_id_external=f"<m-{company}-{offset_days}-{subject[:12]}@x>",
        sender_email="scheduler@example.com",
        subject=subject,
        snippet=snippet,
        received_at=when,
        classification=classification,
        extracted_company=company,
        classification_at=when,
        application_id=application_id,
    )
    session.add(msg)
    await session.flush()
    return msg, thread


async def _seed_application(session, *, user_id: int, company: str, role: str = "SWE", status=None):
    from models import Application
    from models.enums import ApplicationStatus

    a = Application(
        user_id=user_id,
        company=company,
        role=role,
        status=status or ApplicationStatus.ONSITE_LOOP,
    )
    session.add(a)
    await session.flush()
    return a


# ── Reclassify ──────────────────────────────────────────────────────────


async def test_reclassify_persists_correction_and_reruns_dispatch(session, user):
    """follow_up → rejection on a linked application: correction row written,
    human label pinned, and the dispatch derives the CLOSED suggestion
    (human-confirm — never auto-applied)."""
    from sqlmodel import select

    from models import ClassificationCorrection
    from models.enums import ApplicationStatus, EmailClassification
    from services.email import corrections

    application = await _seed_application(session, user_id=user.id, company="ByteDance")
    msg, thread = await _seed_message(
        session,
        user_id=user.id,
        company="ByteDance",
        classification=EmailClassification.FOLLOW_UP,
        subject="Update on your application",
        application_id=application.id,
    )

    out = await corrections.reclassify_message(
        session,
        user_id=user.id,
        message_id=msg.id,
        to_classification=EmailClassification.REJECTION,
    )

    assert out.classification == EmailClassification.REJECTION
    assert out.auto_classified is False
    # Dispatch re-ran: rejection on a live application → CLOSED suggestion,
    # NOT auto-applied (asymmetric autonomy).
    assert out.suggested_status == ApplicationStatus.CLOSED
    assert out.suggestion_applied_at is None
    assert application.status == ApplicationStatus.ONSITE_LOOP

    row = (await session.exec(select(ClassificationCorrection))).one()
    assert row.kind == "reclassify"
    assert row.from_classification == "follow_up"
    assert row.to_classification == "rejection"
    assert row.user_id == user.id

    # Thread mirrors the human label and is pinned against auto-promotion.
    assert thread.classification == EmailClassification.REJECTION
    assert thread.manually_verified is True


async def test_reclassify_links_unlinked_message_by_company(session, user):
    """Dispatch re-run includes the company→application linking step."""
    from models.enums import EmailClassification
    from services.email import corrections

    application = await _seed_application(session, user_id=user.id, company="Camber")
    msg, thread = await _seed_message(
        session,
        user_id=user.id,
        company="Camber",
        classification=EmailClassification.OTHER,
        subject="System design round",
    )
    assert msg.application_id is None

    await corrections.reclassify_message(
        session,
        user_id=user.id,
        message_id=msg.id,
        to_classification=EmailClassification.INTERVIEW_REQUEST,
    )
    assert msg.application_id == application.id
    assert thread.application_id == application.id


async def test_reclassify_idor_rejected(session, user):
    from models import User
    from models.enums import EmailClassification
    from services.email import corrections

    other = User(email="other@example.com", password_hash="x", is_active=True)
    session.add(other)
    await session.flush()
    msg, _ = await _seed_message(
        session,
        user_id=other.id,
        company="Ripple",
        classification=EmailClassification.OTHER,
    )
    with pytest.raises(corrections.CorrectionError):
        await corrections.reclassify_message(
            session,
            user_id=user.id,
            message_id=msg.id,
            to_classification=EmailClassification.REJECTION,
        )


# ── Unlink ──────────────────────────────────────────────────────────────


async def test_unlink_thread_clears_links_and_stamps_correction(session, user):
    from sqlmodel import select

    from models import ClassificationCorrection
    from models.enums import EmailClassification
    from services.email import corrections

    application = await _seed_application(session, user_id=user.id, company="Mosaic")
    msg, thread = await _seed_message(
        session,
        user_id=user.id,
        company="Mosaic",
        classification=EmailClassification.INTERVIEW_REQUEST,
        application_id=application.id,
    )

    n = await corrections.unlink_thread(session, user_id=user.id, thread_id=thread.id)
    assert n == 1
    assert thread.application_id is None
    assert msg.application_id is None

    row = (await session.exec(select(ClassificationCorrection))).one()
    assert row.kind == "unlink"
    assert row.from_company == "Mosaic"

    # Unlinking a never-linked thread is a 404-shaped error, not a no-op.
    with pytest.raises(corrections.CorrectionError):
        await corrections.unlink_thread(session, user_id=user.id, thread_id=thread.id)


# ── Merge / aliases ─────────────────────────────────────────────────────


async def test_merge_company_aliases_groups_and_survives_regroup(session, user):
    """Two canonically-distinct groups merge via alias; the alias holds on
    every later regroup (it is consulted by grouping, not applied once)."""
    from models.enums import EmailClassification
    from services.email import corrections, processes

    await _seed_message(
        session,
        user_id=user.id,
        company="Mosaic",
        classification=EmailClassification.INTERVIEW_REQUEST,
        offset_days=3,
    )
    await _seed_message(
        session,
        user_id=user.id,
        company="Mosaic Building Group",
        classification=EmailClassification.ASSESSMENT,
        offset_days=1,
        subject="Your take-home",
    )

    detected = await processes.list_detected_processes(session, user_id=user.id)
    assert len(detected) == 2  # canonical keys differ pre-alias

    await corrections.merge_company(
        session, user_id=user.id, from_company="Mosaic Building Group", to_company="Mosaic"
    )

    for _ in range(2):  # alias survives regroup after regroup
        detected = await processes.list_detected_processes(session, user_id=user.id)
        assert len(detected) == 1
        assert detected[0].message_count == 2


async def test_merge_company_relinks_to_live_application(session, user):
    from models.enums import EmailClassification
    from services.email import corrections

    application = await _seed_application(session, user_id=user.id, company="Mosaic")
    msg, thread = await _seed_message(
        session,
        user_id=user.id,
        company="Mosaic Building Group",
        classification=EmailClassification.INTERVIEW_REQUEST,
    )

    relinked = await corrections.merge_company(
        session, user_id=user.id, from_company="Mosaic Building Group", to_company="Mosaic"
    )
    assert relinked == 1
    assert msg.application_id == application.id
    assert thread.application_id == application.id


async def test_merge_same_canonical_key_rejected(session, user):
    from services.email import corrections

    with pytest.raises(corrections.CorrectionError):
        await corrections.merge_company(
            session, user_id=user.id, from_company="Brico.ai", to_company="Brico"
        )


# ── Rejection-guard chip (§ 3.4.4) ──────────────────────────────────────


async def test_rejection_shaped_follow_up_flags_group(session, user):
    """Interview signals + a LATER rejection-shaped follow_up → the group
    carries the confirm chip; the derived status is untouched."""
    from models.enums import ApplicationStatus, EmailClassification
    from services.email import processes

    await _seed_message(
        session,
        user_id=user.id,
        company="Camber",
        classification=EmailClassification.INTERVIEW_REQUEST,
        offset_days=5,
    )
    stray, _ = await _seed_message(
        session,
        user_id=user.id,
        company="Camber",
        classification=EmailClassification.FOLLOW_UP,
        subject="Your application at Camber",
        snippet="We have decided to move forward with other candidates for this role.",
        offset_days=1,
    )

    detected = await processes.list_detected_processes(session, user_id=user.id)
    assert len(detected) == 1
    assert detected[0].possible_rejection_message_id == stray.id
    assert detected[0].status != ApplicationStatus.CLOSED  # chip only, no flip


async def test_plain_follow_up_does_not_flag_group(session, user):
    from models.enums import EmailClassification
    from services.email import processes

    await _seed_message(
        session,
        user_id=user.id,
        company="Camber",
        classification=EmailClassification.INTERVIEW_REQUEST,
        offset_days=5,
    )
    await _seed_message(
        session,
        user_id=user.id,
        company="Camber",
        classification=EmailClassification.FOLLOW_UP,
        subject="Checking in",
        snippet="Just confirming Thursday works for the panel.",
        offset_days=1,
    )
    detected = await processes.list_detected_processes(session, user_id=user.id)
    assert detected[0].possible_rejection_message_id is None


# ── Route pins: CSRF (403 before any handler state) ─────────────────────


@pytest.mark.uses_sample_data_shims
@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/api/v1/email/messages/1/reclassify", {"classification": "rejection"}),
        ("/api/v1/email/threads/1/unlink", {}),
        ("/api/v1/tracking/processes/merge", {"company": "A", "target": "B"}),
    ],
)
def test_correction_routes_require_csrf(path: str, body: dict):
    from fastapi.testclient import TestClient

    from main import app

    client = TestClient(app, raise_server_exceptions=True)
    client.cookies.set("naavik_session", "fake-1")  # authed, no CSRF pair
    resp = client.post(path, data=body)
    assert resp.status_code == 403, f"POST {path} should 403 without CSRF, got {resp.status_code}"
