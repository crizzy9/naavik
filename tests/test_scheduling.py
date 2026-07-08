"""Scheduling assistant (plan 96 slice 96f).

Slot engine DST/tz matrix (pure), the `action_needed` deterministic
post-check, needs-scheduling detection, the draft service (fake LLM,
NOTE_ADDED audit event, honest degrade), the Gmail compose deep-link, and
template rendering. The no-send guarantee is pinned separately in
`test_no_send_guard.py`.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

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


_NY = ZoneInfo("America/New_York")
_WINDOW = None  # filled in tests via parse_window


# ── Slot engine (pure) ──────────────────────────────────────────────────


def test_parse_window_valid_and_degraded():
    from datetime import time

    from services.scheduling import parse_window

    assert parse_window("10:00-18:00") == (time(10, 0), time(18, 0))
    assert parse_window("09:30-17:15") == (time(9, 30), time(17, 15))
    # Malformed / inverted / empty degrade to the default band.
    assert parse_window("garbage") == (time(10, 0), time(18, 0))
    assert parse_window("18:00-10:00") == (time(10, 0), time(18, 0))
    assert parse_window(None) == (time(10, 0), time(18, 0))


def test_slots_fall_back_dst_keeps_wall_clock():
    """US DST ends Sun 2026-11-01: Friday runs on EDT (UTC-4), Monday on EST
    (UTC-5). The 10:00 wall-clock window must hold on BOTH sides — the UTC
    offset is what moves."""
    from services.scheduling import free_slots, parse_window

    slots = free_slots(
        busy=[],
        tz=_NY,
        window=parse_window("10:00-18:00"),
        now=datetime(2026, 10, 30, 12, 0, tzinfo=UTC),  # Fri 08:00 EDT
        count=40,
        business_days=2,
    )
    fridays = [s for s in slots if s.starts_at.astimezone(_NY).date().day == 30]
    mondays = [s for s in slots if s.starts_at.astimezone(_NY).date().day == 2]
    assert fridays and mondays
    # Friday: lead (+3h from 08:00 EDT) pushes the first slot to 11:00 EDT.
    assert fridays[0].starts_at == datetime(2026, 10, 30, 15, 0, tzinfo=UTC)
    assert fridays[0].starts_at.astimezone(_NY).hour == 11
    # Monday: 10:00 EST — same 15:00 UTC as Friday's 11:00 EDT.
    assert mondays[0].starts_at == datetime(2026, 11, 2, 15, 0, tzinfo=UTC)
    assert mondays[0].starts_at.astimezone(_NY).hour == 10
    # No weekend slots ever (Oct 31 / Nov 1).
    assert all(s.starts_at.astimezone(_NY).weekday() < 5 for s in slots)


def test_slots_spring_forward_dst():
    """US DST starts Sun 2026-03-08: Friday EST (UTC-5), Monday EDT (UTC-4)."""
    from services.scheduling import free_slots, parse_window

    slots = free_slots(
        busy=[],
        tz=_NY,
        window=parse_window("10:00-18:00"),
        now=datetime(2026, 3, 6, 12, 0, tzinfo=UTC),  # Fri 07:00 EST
        count=40,
        business_days=2,
    )
    fridays = [s for s in slots if s.starts_at.astimezone(_NY).date().day == 6]
    mondays = [s for s in slots if s.starts_at.astimezone(_NY).date().day == 9]
    assert fridays[0].starts_at == datetime(2026, 3, 6, 15, 0, tzinfo=UTC)  # 10:00 EST
    assert mondays[0].starts_at == datetime(2026, 3, 9, 14, 0, tzinfo=UTC)  # 10:00 EDT


def test_slots_skip_busy_and_weekends():
    from services.scheduling import free_slots, parse_window

    now = datetime(2026, 7, 11, 12, 0, tzinfo=UTC)  # Saturday
    busy = [(datetime(2026, 7, 13, 15, 0, tzinfo=UTC), datetime(2026, 7, 13, 16, 0, tzinfo=UTC))]
    slots = free_slots(busy=busy, tz=_NY, window=parse_window("10:00-18:00"), now=now, count=3)
    assert slots
    # First eligible day is Monday Jul 13; 10:00 EDT = 14:00 UTC.
    first = slots[0]
    assert first.starts_at == datetime(2026, 7, 13, 14, 0, tzinfo=UTC)
    # The 15:00-16:00 UTC busy block excludes any overlapping candidate.
    for s in slots:
        assert not (s.starts_at < busy[0][1] and busy[0][0] < s.ends_at)


def test_slot_count_honored():
    from services.scheduling import free_slots, parse_window

    slots = free_slots(
        busy=[],
        tz=_NY,
        window=parse_window("10:00-18:00"),
        now=datetime(2026, 7, 13, 8, 0, tzinfo=UTC),
        count=5,
    )
    assert len(slots) == 5


def test_format_slot_carries_explicit_zone():
    from services.scheduling import Slot, format_slot

    label = format_slot(
        Slot(
            starts_at=datetime(2026, 7, 13, 14, 0, tzinfo=UTC),
            ends_at=datetime(2026, 7, 13, 14, 45, tzinfo=UTC),
        ),
        _NY,
    )
    assert "EDT" in label
    assert "Jul 13" in label


# ── action_needed post-check ────────────────────────────────────────────


def test_action_needed_post_check_requires_corroboration():
    from services.scheduling import action_needed_post_check

    text = "please send us your availability for next week"
    assert action_needed_post_check("send_availability", text=text) == "send_availability"
    # The label must be corroborated — a claim without keywords degrades.
    assert action_needed_post_check("pick_slot", text=text) is None
    assert action_needed_post_check("confirm_time", text="does this work for you?") == (
        "confirm_time"
    )
    assert action_needed_post_check("pick_slot", text="book a time via calendly") == "pick_slot"
    assert action_needed_post_check("none", text=text) is None
    assert action_needed_post_check(None, text=text) is None
    assert action_needed_post_check("made_up_label", text=text) is None


# ── Gmail compose deep-link ─────────────────────────────────────────────


def test_gmail_compose_url_is_a_compose_deeplink():
    from services.scheduling import gmail_compose_url

    url = gmail_compose_url(to="r@x.co", subject="Re: Interview", body="A" * 3000)
    assert url.startswith("https://mail.google.com/mail/?")
    assert "view=cm" in url
    assert "to=r%40x.co" in url
    assert "su=Re%3A+Interview" in url
    # Body truncates at the compose budget (~1600) — Copy is primary.
    from urllib.parse import parse_qs, urlsplit

    body = parse_qs(urlsplit(url).query)["body"][0]
    assert len(body) == 1600


# ── DB-backed: detection + draft ────────────────────────────────────────


def _tables():
    from sqlalchemy import CheckConstraint

    from models import (
        AppEvent,
        Application,
        CalendarEvent,
        EmailInvite,
        EmailMessage,
        EmailThread,
        Job,
        Profile,
        Settings,
        User,
    )

    tables = [
        User.__table__,
        Job.__table__,
        Profile.__table__,
        Application.__table__,
        AppEvent.__table__,
        EmailThread.__table__,
        EmailMessage.__table__,
        EmailInvite.__table__,
        CalendarEvent.__table__,
        Settings.__table__,
    ]
    for table in tables:
        for c in list(table.constraints):
            if isinstance(c, CheckConstraint):
                table.constraints.discard(c)
        for idx in list(table.indexes):
            if "gin" in (idx.name or "").lower():
                table.indexes.discard(idx)
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

    u = User(email="sched@example.com", password_hash="x", is_active=True)
    session.add(u)
    await session.flush()
    return u


async def _make_application(session, user, *, status=None, artifacts=None, company="Chime"):
    from models import Application
    from models.enums import ApplicationStatus

    a = Application(
        user_id=user.id,
        company=company,
        role="Senior Software Engineer",
        status=status or ApplicationStatus.ONSITE_LOOP,
        submission_artifacts=artifacts or {},
    )
    session.add(a)
    await session.flush()
    return a


_SEQ = iter(range(1, 10_000))


async def _make_message(
    session,
    user,
    application,
    *,
    thread=None,
    action_needed=None,
    subject="Please send your availability",
    received_at=None,
    urgency=None,
):
    from models import EmailMessage, EmailThread
    from models.enums import EmailClassification

    n = next(_SEQ)
    if thread is None:
        thread = EmailThread(
            user_id=user.id,
            provider="imap",
            thread_id_external=f"<st{n}@x>",
            subject=subject,
            classification=EmailClassification.INTERVIEW_REQUEST,
            latest_message_at=received_at or datetime(2026, 7, 7, tzinfo=UTC),
            message_count=1,
            application_id=application.id,
        )
        session.add(thread)
        await session.flush()
    msg = EmailMessage(
        user_id=user.id,
        thread_id=thread.id,
        application_id=application.id,
        provider="imap",
        message_id_external=f"<sm{n}@x>",
        sender_email="recruiting@chime.com",
        subject=subject,
        snippet="please share your availability",
        body_excerpt="Could you send over a few times that work next week?",
        received_at=received_at or datetime(2026, 7, 7, tzinfo=UTC),
        classification=EmailClassification.INTERVIEW_REQUEST,
        action_needed=action_needed,
        urgency=urgency,
    )
    session.add(msg)
    await session.flush()
    return msg, thread


async def test_needs_scheduling_from_action_needed(session, user):
    from services.scheduling import list_needs_scheduling

    app = await _make_application(session, user)
    await _make_message(session, user, app, action_needed="send_availability")
    rows = await list_needs_scheduling(session, user_id=user.id)
    assert len(rows) == 1
    assert rows[0].application_id == app.id
    assert rows[0].action == "send_availability"
    assert rows[0].action_label == "send availability"


async def test_needs_scheduling_drops_when_conversation_moves_on(session, user):
    from services.scheduling import list_needs_scheduling

    app = await _make_application(session, user)
    _, thread = await _make_message(
        session,
        user,
        app,
        action_needed="send_availability",
        received_at=datetime(2026, 7, 6, tzinfo=UTC),
    )
    # A LATER message in the same thread means the ask was answered.
    await _make_message(
        session,
        user,
        app,
        thread=thread,
        subject="Re: scheduled!",
        received_at=datetime(2026, 7, 7, tzinfo=UTC),
    )
    rows = await list_needs_scheduling(session, user_id=user.id)
    assert rows == []


async def test_needs_scheduling_from_reconcile_stamp(session, user):
    from services.scheduling import list_needs_scheduling

    app = await _make_application(
        session,
        user,
        artifacts={
            "reconcile": {
                "needs_scheduling": {
                    "thread_id": 1,
                    "subject": "Interview with Chime",
                    "detected_at": "2026-07-08T00:00:00+00:00",
                }
            }
        },
    )
    await _make_message(session, user, app, subject="Interview with Chime")
    rows = await list_needs_scheduling(session, user_id=user.id)
    assert len(rows) == 1
    assert rows[0].action == "needs_scheduling"


async def test_needs_scheduling_urgency_orders_first(session, user):
    from services.scheduling import list_needs_scheduling

    calm = await _make_application(session, user, company="SlowCo")
    urgent = await _make_application(session, user, company="FastCo")
    await _make_message(session, user, calm, action_needed="pick_slot", urgency="low")
    await _make_message(session, user, urgent, action_needed="confirm_time", urgency="high")
    rows = await list_needs_scheduling(session, user_id=user.id)
    assert [r.company for r in rows] == ["FastCo", "SlowCo"]


async def test_draft_builds_body_and_audit_event(session, user, monkeypatch):
    import llm as llm_module
    from models import AppEvent, Settings
    from models.enums import AppEventKind
    from services import llm_tracker
    from services.scheduling import build_scheduling_draft

    session.add(Settings(user_id=user.id))
    app = await _make_application(session, user)
    msg, _ = await _make_message(session, user, app, action_needed="send_availability")

    class _Provider:
        model = "fake"

    async def _fake_tracked_call(**kwargs):
        assert "Chime" in kwargs["prompt"]
        return type("R", (), {"value": {"body": "Happy to! Any of these work:\n- slot"}})()

    monkeypatch.setattr(llm_module, "get_provider", lambda _s: _Provider())
    monkeypatch.setattr(llm_tracker, "tracked_call", _fake_tracked_call)

    draft = await build_scheduling_draft(session, user_id=user.id, application_id=app.id)
    assert draft.body and "Happy to" in draft.body
    assert draft.to == "recruiting@chime.com"
    assert draft.subject.startswith("Re: ")
    assert draft.gmail_url and "view=cm" in draft.gmail_url
    assert len(draft.slot_labels) == 3

    from sqlmodel import select

    events = (
        await session.exec(select(AppEvent).where(AppEvent.kind == AppEventKind.NOTE_ADDED))
    ).all()
    assert len(events) == 1
    payload = events[0].payload
    assert payload.get("source") == "scheduling_draft"
    assert payload.get("drafted") is True
    assert payload.get("message_id") == msg.id
    # The prose is NOT persisted — auditability without storage.
    assert "Happy to" not in json.dumps(payload)


async def test_draft_degrades_without_provider(session, user, monkeypatch):
    import llm as llm_module
    from models import Settings
    from services.scheduling import build_scheduling_draft

    session.add(Settings(user_id=user.id))
    app = await _make_application(session, user)
    await _make_message(session, user, app, action_needed="send_availability")

    def _no_provider(_s):
        raise llm_module.LLMProviderError("no keys", kind="auth_required")

    monkeypatch.setattr(llm_module, "get_provider", _no_provider)
    draft = await build_scheduling_draft(session, user_id=user.id, application_id=app.id)
    assert draft.body is None
    assert draft.gmail_url is None
    assert draft.slot_labels  # slots still render
    assert draft.degraded_reason


async def test_draft_404_on_foreign_application(session, user):
    from models import User
    from services.scheduling import SchedulingError, build_scheduling_draft

    other = User(email="other@example.com", password_hash="x", is_active=True)
    session.add(other)
    await session.flush()
    app = await _make_application(session, user)
    with pytest.raises(SchedulingError):
        await build_scheduling_draft(session, user_id=other.id, application_id=app.id)


# ── Template rendering ──────────────────────────────────────────────────


def _env():
    from jinja2 import ChainableUndefined, Environment, FileSystemLoader

    return Environment(
        loader=FileSystemLoader("src/ui/templates"),
        autoescape=True,
        undefined=ChainableUndefined,
    )


def test_needs_scheduling_strip_renders():
    html = (
        _env()
        .get_template("components/tracking/_needs_scheduling_strip.html")
        .render(
            needs_scheduling=[
                {
                    "application_id": 7,
                    "company": "Chime",
                    "role": "Senior SWE",
                    "action_label": "send availability",
                    "subject": "Please send your availability",
                    "detected_label": "2h ago",
                    "urgency": "high",
                    "dom_id": "needs-scheduling-7",
                }
            ]
        )
    )
    assert "needs-scheduling-strip" in html
    assert "Suggest times" in html
    assert 'hx-post="/_fragments/tracking/scheduling/7"' in html
    assert "urgent" in html


def test_needs_scheduling_strip_empty_renders_nothing():
    html = (
        _env()
        .get_template("components/tracking/_needs_scheduling_strip.html")
        .render(needs_scheduling=[])
    )
    assert html.strip() == ""


def test_scheduling_draft_panel_renders_copy_and_gmail():
    html = (
        _env()
        .get_template("components/tracking/_scheduling_draft_panel.html")
        .render(
            draft={
                "application_id": 7,
                "company": "Chime",
                "slot_labels": ["Thu Jul 9, 10:00–10:45 am EDT"],
                "tz_label": "EDT",
                "body": "Happy to — any of these work.",
                "to": "recruiting@chime.com",
                "subject": "Re: availability",
                "gmail_url": "https://mail.google.com/mail/?view=cm&fs=1",
                "degraded_reason": None,
            }
        )
    )
    assert "scheduling-draft-panel" in html
    assert "Copy draft" in html
    assert "Open in Gmail" in html
    assert "Naavik never sends" in html
