"""Plan 96b — the /emails log: ctx derivation, filters, keyset pagination,
IDOR scoping, and the per-email signal-detail component."""

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
        EmailAccount.__table__,
        EmailThread.__table__,
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
        s.add(User(id=1, email="log@x.test", password_hash="x", is_active=True))
        s.add(User(id=2, email="other@x.test", password_hash="x", is_active=True))
        await s.flush()
        yield s
    await engine.dispose()


_BASE_TS = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)


async def _seed(
    session,
    *,
    user_id: int = 1,
    subject: str = "hello",
    sender: str = "person@corp.com",
    classification=None,
    company: str | None = None,
    end_client: str | None = None,
    sender_type: str | None = None,
    application_id: int | None = None,
    dismissed: bool = False,
    minutes_ago: int = 0,
    suggested_status=None,
    suggestion_applied: bool = False,
):
    from models import EmailMessage, EmailThread
    from models.enums import EmailClassification

    when = _BASE_TS - timedelta(minutes=minutes_ago)
    thread = EmailThread(
        user_id=user_id,
        provider="imap",
        thread_id_external=f"<t-{subject[:16]}-{minutes_ago}@x>",
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
        message_id_external=f"<m-{subject[:16]}-{minutes_ago}@x>",
        sender_email=sender,
        sender_name=sender.split("@")[0].title(),
        subject=subject,
        snippet="…",
        received_at=when,
        classification=classification,
        extracted_company=company,
        extracted_end_client=end_client,
        extracted_sender_type=sender_type,
        application_id=application_id,
        process_dismissed_at=when if dismissed else None,
        suggested_status=suggested_status,
        suggested_at=when if suggested_status else None,
        suggestion_applied_at=when if suggestion_applied else None,
    )
    session.add(msg)
    await session.flush()
    return msg


async def _seed_application(session, *, user_id: int = 1, company: str = "Anthuria"):
    from models import Application
    from models.enums import ApplicationStatus

    app = Application(
        user_id=user_id,
        company=company,
        role="Engineer",
        status=ApplicationStatus.RECRUITER_SCREEN,
    )
    session.add(app)
    await session.flush()
    return app


async def _build(session, **kw):
    from ui.email_log_ctx import build_email_log_ctx

    return await build_email_log_ctx(session, user_id=kw.pop("user_id", 1), **kw)


# ── Link-state derivation ────────────────────────────────────────────────


async def test_link_states_cover_every_bucket(session):
    from models.enums import EmailClassification

    app = await _seed_application(session)
    await _seed(
        session,
        subject="linked",
        application_id=app.id,
        minutes_ago=1,
        classification=EmailClassification.INTERVIEW_REQUEST,
    )
    await _seed(
        session,
        subject="detected",
        company="NewCo",
        minutes_ago=2,
        classification=EmailClassification.INTERVIEW_REQUEST,
    )
    await _seed(
        session,
        subject="parked",
        company="G2i",
        sender_type="agency_recruiter",
        minutes_ago=3,
        classification=EmailClassification.INTERVIEW_REQUEST,
    )
    await _seed(
        session,
        subject="dismissed",
        company="GoneCo",
        dismissed=True,
        minutes_ago=4,
        classification=EmailClassification.INTERVIEW_REQUEST,
    )
    await _seed(session, subject="nothing", classification=EmailClassification.OTHER, minutes_ago=5)
    await _seed(session, subject="pending-one", minutes_ago=6)

    ctx = await _build(session)
    states = {r["subject"]: r["link_state"] for r in ctx["rows"]}
    assert states["linked"] == "linked"
    assert states["detected"] == "detected"
    assert states["parked"] == "parked"
    assert states["dismissed"] == "dismissed"
    assert states["nothing"] == "none"
    by_subject = {r["subject"]: r for r in ctx["rows"]}
    assert by_subject["linked"]["linked_company"] == "Anthuria"
    assert by_subject["pending-one"]["classification"] == "pending"
    assert by_subject["pending-one"]["is_pending"] is True
    assert ctx["unclassified_count"] == 1
    assert ctx["total_count"] == 6


# ── Filters ──────────────────────────────────────────────────────────────


async def test_classification_and_pending_filters(session):
    from models.enums import EmailClassification

    await _seed(session, subject="rej", classification=EmailClassification.REJECTION)
    await _seed(session, subject="off", classification=EmailClassification.OFFER, minutes_ago=1)
    await _seed(session, subject="pend", minutes_ago=2)

    ctx = await _build(session, classification="rejection")
    assert [r["subject"] for r in ctx["rows"]] == ["rej"]
    ctx = await _build(session, classification="pending")
    assert [r["subject"] for r in ctx["rows"]] == ["pend"]
    ctx = await _build(session)
    assert len(ctx["rows"]) == 3


async def test_link_state_and_sender_filters(session):
    from models.enums import EmailClassification

    app = await _seed_application(session)
    await _seed(
        session,
        subject="mine",
        application_id=app.id,
        sender="recruiter@anthuria.com",
        classification=EmailClassification.FOLLOW_UP,
    )
    await _seed(
        session,
        subject="loose",
        sender="noreply@job-board.io",
        minutes_ago=1,
        classification=EmailClassification.OTHER,
    )

    ctx = await _build(session, link_state="linked")
    assert [r["subject"] for r in ctx["rows"]] == ["mine"]
    ctx = await _build(session, link_state="none")
    assert [r["subject"] for r in ctx["rows"]] == ["loose"]
    ctx = await _build(session, sender_q="anthuria")
    assert [r["subject"] for r in ctx["rows"]] == ["mine"]
    ctx = await _build(session, sender_q="Noreply")
    assert [r["subject"] for r in ctx["rows"]] == ["loose"]


async def test_date_range_filter(session):
    from models.enums import EmailClassification

    await _seed(session, subject="recent", minutes_ago=0, classification=EmailClassification.OTHER)
    await _seed(
        session,
        subject="ancient",
        minutes_ago=60 * 24 * 30,
        classification=EmailClassification.OTHER,
    )
    ctx = await _build(session, date_from="2026-06-25")
    assert [r["subject"] for r in ctx["rows"]] == ["recent"]
    ctx = await _build(session, date_to="2026-06-25")
    assert [r["subject"] for r in ctx["rows"]] == ["ancient"]


# ── Keyset pagination ────────────────────────────────────────────────────


async def test_keyset_pagination_no_overlap_no_gap(session):
    from models.enums import EmailClassification

    for i in range(60):
        await _seed(
            session,
            subject=f"msg-{i:02d}",
            minutes_ago=i,
            classification=EmailClassification.OTHER,
        )
    page1 = await _build(session)
    assert len(page1["rows"]) == 50
    assert page1["has_more"] is True
    assert page1["next_cursor"]
    page2 = await _build(session, cursor=page1["next_cursor"])
    assert len(page2["rows"]) == 10
    assert page2["has_more"] is False
    seen = [r["subject"] for r in page1["rows"]] + [r["subject"] for r in page2["rows"]]
    assert len(seen) == len(set(seen)) == 60
    # Newest first throughout.
    assert seen[0] == "msg-00" and seen[-1] == "msg-59"


# ── IDOR ─────────────────────────────────────────────────────────────────


async def test_rows_are_user_scoped(session):
    from models.enums import EmailClassification

    await _seed(session, subject="mine", classification=EmailClassification.OTHER)
    await _seed(session, user_id=2, subject="theirs", classification=EmailClassification.OTHER)
    ctx = await _build(session)
    assert [r["subject"] for r in ctx["rows"]] == ["mine"]
    assert ctx["total_count"] == 1


# ── Signal detail — transition outcome from message + event payload ─────


async def test_signal_detail_outcomes(session):
    from models import AppEvent
    from models.enums import AppEventKind, ApplicationStatus, EmailClassification

    app = await _seed_application(session)
    await _seed(
        session,
        subject="auto",
        application_id=app.id,
        minutes_ago=1,
        classification=EmailClassification.INTERVIEW_REQUEST,
        suggested_status=ApplicationStatus.ONSITE_LOOP,
        suggestion_applied=True,
    )
    suppressed = await _seed(
        session,
        subject="pinned",
        application_id=app.id,
        minutes_ago=2,
        classification=EmailClassification.INTERVIEW_REQUEST,
        suggested_status=ApplicationStatus.ONSITE_LOOP,
    )
    await _seed(
        session,
        subject="waiting",
        application_id=app.id,
        minutes_ago=3,
        classification=EmailClassification.REJECTION,
        suggested_status=ApplicationStatus.CLOSED,
    )
    session.add(
        AppEvent(
            user_id=1,
            application_id=app.id,
            kind=AppEventKind.EMAIL_STATUS_SUGGESTED,
            payload={
                "message_id": suppressed.id,
                "current_status": "RECRUITER_SCREEN",
                "suggested_status": "ONSITE_LOOP",
                "applied": False,
                "suppressed_by_pin": True,
            },
        )
    )
    await session.flush()

    ctx = await _build(session)
    by_subject = {r["subject"]: r for r in ctx["rows"]}
    assert by_subject["auto"]["suggestion"]["outcome"] == "applied"
    assert by_subject["pinned"]["suggestion"]["outcome"] == "suppressed_by_pin"
    assert by_subject["pinned"]["suggestion"]["from_label"] == "Recruiter Screen"
    assert by_subject["waiting"]["suggestion"]["outcome"] == "pending"


# ── Template render — row + signal detail + load-more wiring ─────────────


def _render_page(**overrides):
    from ui.templates_setup import templates

    ctx = {
        "rows": [],
        "has_more": False,
        "next_cursor": None,
        "filters": {
            "classification": "",
            "link_state": "",
            "account_id": "",
            "date_from": "",
            "date_to": "",
            "sender_q": "",
        },
    }
    ctx.update(overrides)
    tpl = templates.env.get_template("components/email/_email_log_page.html")
    return tpl.render(**ctx)


def _row(**overrides):
    base = {
        "id": 9,
        "received_label": "2d ago",
        "received_title": "2026-07-06 12:00 UTC",
        "sender_name": "Recruiter",
        "sender_email": "r@corp.com",
        "sender_domain": "corp.com",
        "subject": "Interview loop",
        "snippet": "snippet text",
        "classification": "interview_request",
        "classification_tone": "indigo",
        "is_pending": False,
        "unclassified_reason": None,
        "link_state": "linked",
        "linked_company": "Corp",
        "application_id": 4,
        "extracted_company": "Corp",
        "extracted_role": "Engineer",
        "extracted_stage": "interview",
        "extracted_round_kind": "system_design",
        "extracted_sender_type": "employer",
        "extracted_end_client": None,
        "urgency": "high",
        "suggestion": {
            "from_label": "Applied",
            "status_label": "Interview Stage",
            "outcome": "applied",
        },
        "body_excerpt": None,
        "can_fetch_body": True,
        "provider_link": "https://mail.google.com/mail/u/0/#search/rfc822msgid:x",
    }
    base.update(overrides)
    return base


def test_row_renders_chips_actions_and_signal_detail():
    html = _render_page(rows=[_row()])
    assert 'data-testid="email-row-9"' in html
    assert "linked → Corp" in html
    assert 'href="/tracking/4"' in html
    assert 'data-testid="log-reclassify-9-rejection"' in html
    assert 'data-testid="log-flag-9-agency"' in html
    assert 'data-testid="log-load-body-9"' in html
    assert 'data-testid="signal-detail-9"' in html
    assert "auto-applied" in html
    assert "system design" in html


def test_pending_row_and_suppressed_outcome():
    html = _render_page(
        rows=[
            _row(
                id=11,
                is_pending=True,
                classification="pending",
                classification_tone="slate",
                unclassified_reason="llm_failed",
                link_state="none",
                suggestion={
                    "from_label": None,
                    "status_label": "Closed",
                    "outcome": "suppressed_by_pin",
                },
            )
        ]
    )
    assert ">pending<" in html
    assert "held by your pin" in html


def test_load_more_carries_cursor_and_filters():
    html = _render_page(
        rows=[_row()],
        has_more=True,
        next_cursor="2026-07-01T12:00:00+00:00|9",
        filters={
            "classification": "rejection",
            "link_state": "",
            "account_id": "",
            "date_from": "",
            "date_to": "",
            "sender_q": "acme",
        },
    )
    assert 'data-testid="email-log-load-more"' in html
    assert "cursor=" in html
    assert "classification=rejection" in html
    assert "sender_q=acme" in html


def test_empty_page_renders_empty_state():
    html = _render_page()
    assert 'data-testid="email-log-empty"' in html
    assert 'data-testid="email-log-load-more"' not in html


# ── Route smoke (sample-data shims) ──────────────────────────────────────


@pytest.mark.uses_sample_data_shims
def test_emails_page_renders_with_sidebar_entry():
    from fastapi.testclient import TestClient

    from main import app

    client = TestClient(app, raise_server_exceptions=True)
    client.cookies.set("naavik_session", "fake-1")
    r = client.get("/emails")
    assert r.status_code == 200
    assert 'data-testid="email-log-filters"' in r.text
    assert 'id="email-log-list"' in r.text
    assert 'href="/emails"' in r.text  # sidebar entry
