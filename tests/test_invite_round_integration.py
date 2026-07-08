"""Invite chains → interview rounds (plan 96 slice 96d).

The invite is the SCHEDULING axis, the round is the INTERVIEW axis (owner
decision 2026-07-08): a live chain guarantees one riding round, a reschedule
SHIFTS every rider by the container delta, a cancellation without
replacement reverts riders to `planned`, and rounds renumber chronologically.
Plus the sync-time ingest hook (fake IMAP) and the past-due completion rider.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime
from email.message import EmailMessage as MIMEMessage

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
        CalendarEvent,
        EmailAccount,
        EmailInvite,
        EmailMessage,
        EmailThread,
        InterviewRound,
        Job,
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
        EmailInvite.__table__,
        InterviewRound.__table__,
        CalendarEvent.__table__,
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

    u = User(email="invites@example.com", password_hash="x", is_active=True)
    session.add(u)
    await session.flush()
    return u


@pytest.fixture
async def application(session, user):
    from models import Application
    from models.enums import ApplicationStatus

    a = Application(
        user_id=user.id,
        company="Headway",
        role="Senior Backend Software Engineer",
        status=ApplicationStatus.RECRUITER_SCREEN,
        applied_at=datetime(2026, 6, 1, tzinfo=UTC),
    )
    session.add(a)
    await session.flush()
    return a


async def _make_message(session, user, application=None, *, subject="Invitation: Interview"):
    from models import EmailMessage, EmailThread
    from models.enums import EmailClassification

    thread = EmailThread(
        user_id=user.id,
        provider="imap",
        thread_id_external=f"<t-{subject}-{id(subject)}@x>",
        subject=subject,
        classification=EmailClassification.INTERVIEW_REQUEST,
        latest_message_at=datetime(2026, 7, 7, tzinfo=UTC),
        message_count=1,
        application_id=application.id if application else None,
    )
    session.add(thread)
    await session.flush()
    msg = EmailMessage(
        user_id=user.id,
        thread_id=thread.id,
        application_id=application.id if application else None,
        provider="imap",
        message_id_external=f"<m-{id(thread)}@x>",
        sender_email="invites@ashbyhq.com",
        subject=subject,
        snippet="",
        received_at=datetime(2026, 7, 7, tzinfo=UTC),
        classification=EmailClassification.INTERVIEW_REQUEST,
    )
    session.add(msg)
    await session.flush()
    return msg


def _ics(
    *,
    uid: str = "uid-headway-1@google.com",
    seq: int = 0,
    method: str = "REQUEST",
    status: str = "CONFIRMED",
    start: str = "20260715T110000",
    end: str = "20260715T120000",
    summary: str = "Interview with Headway | Shyam Padia",
) -> str:
    return (
        "BEGIN:VCALENDAR\n"
        "PRODID:-//Google Inc//Google Calendar 70.9054//EN\n"
        "VERSION:2.0\n"
        f"METHOD:{method}\n"
        "BEGIN:VEVENT\n"
        f"DTSTART;TZID=America/Los_Angeles:{start}\n"
        f"DTEND;TZID=America/Los_Angeles:{end}\n"
        f"UID:{uid}\n"
        f"SEQUENCE:{seq}\n"
        f"STATUS:{status}\n"
        f"SUMMARY:{summary}\n"
        "END:VEVENT\n"
        "END:VCALENDAR\n"
    )


def _mime(ics: str, *, method: str = "REQUEST") -> MIMEMessage:
    m = MIMEMessage()
    m["Message-ID"] = "<x@example.com>"
    m["From"] = "Interviews <invites@ashbyhq.com>"
    m["Subject"] = "Invitation: Interview with Headway"
    m.set_content("You have been invited.")
    m.add_attachment(ics.encode(), maintype="text", subtype="calendar", params={"method": method})
    return m


async def _ingest_and_apply(session, msg, application, ics: str, *, method: str = "REQUEST"):
    from services.email import invites

    rows = await invites.ingest_message_invites(session, msg, _mime(ics, method=method))
    await invites.apply_invites_for_application(session, application=application)
    return rows


# ── Ingest ──────────────────────────────────────────────────────────────


async def test_ingest_is_idempotent(session, user, application):
    from sqlmodel import select

    from models import EmailInvite
    from services.email import invites

    msg = await _make_message(session, user, application)
    mime = _mime(_ics())
    await invites.ingest_message_invites(session, msg, mime)
    await invites.ingest_message_invites(session, msg, mime)
    rows = (await session.exec(select(EmailInvite))).all()
    assert len(rows) == 1
    assert rows[0].application_id == application.id
    assert rows[0].starts_at is not None


# ── Chain → round ───────────────────────────────────────────────────────


async def test_live_chain_creates_scheduled_round(session, user, application):
    from services.applications import rounds

    msg = await _make_message(session, user, application)
    await _ingest_and_apply(session, msg, application, _ics())
    rows = await rounds.list_rounds(session, application_id=application.id)
    assert len(rows) == 1
    r = rows[0]
    assert r.invite_uid == "uid-headway-1@google.com"
    assert r.state == "scheduled"
    # 11:00 America/Los_Angeles → 18:00 UTC (sqlite returns naive UTC).
    assert (r.scheduled_at.hour, r.scheduled_at.day) == (18, 15)
    assert r.source == "email"


async def test_reschedule_moves_the_same_round(session, user, application):
    from services.applications import rounds

    msg = await _make_message(session, user, application)
    await _ingest_and_apply(session, msg, application, _ics())
    msg2 = await _make_message(session, user, application, subject="Updated invitation")
    await _ingest_and_apply(
        session, msg2, application, _ics(seq=1, start="20260716T140000", end="20260716T150000")
    )
    rows = await rounds.list_rounds(session, application_id=application.id)
    assert len(rows) == 1  # moved, never a date-keyed sibling
    assert (rows[0].scheduled_at.day, rows[0].scheduled_at.hour) == (16, 21)


async def test_cancel_without_replacement_reverts_to_planned(session, user, application):
    from services.applications import rounds

    msg = await _make_message(session, user, application)
    await _ingest_and_apply(session, msg, application, _ics())
    msg2 = await _make_message(session, user, application, subject="Cancelled")
    await _ingest_and_apply(
        session,
        msg2,
        application,
        _ics(seq=1, method="CANCEL", status="CANCELLED"),
        method="CANCEL",
    )
    rows = await rounds.list_rounds(session, application_id=application.id)
    assert len(rows) == 1
    assert rows[0].state == "planned"
    assert rows[0].scheduled_at is None


async def test_request_after_cancel_reschedules_same_round(session, user, application):
    from services.applications import rounds

    msg = await _make_message(session, user, application)
    await _ingest_and_apply(session, msg, application, _ics())
    msg2 = await _make_message(session, user, application, subject="Cancelled")
    await _ingest_and_apply(
        session,
        msg2,
        application,
        _ics(seq=1, method="CANCEL", status="CANCELLED"),
        method="CANCEL",
    )
    msg3 = await _make_message(session, user, application, subject="New time")
    await _ingest_and_apply(
        session, msg3, application, _ics(seq=2, start="20260717T090000", end="20260717T100000")
    )
    rows = await rounds.list_rounds(session, application_id=application.id)
    assert len(rows) == 1
    assert rows[0].state == "scheduled"
    assert (rows[0].scheduled_at.day, rows[0].scheduled_at.hour) == (17, 16)


async def test_container_reschedule_shifts_all_riders(session, user, application):
    """One calendar event, several interviews (Chime shape): a container
    move shifts every rider, preserving the segment offsets."""
    from services.applications import rounds
    from services.email import invites

    msg = await _make_message(session, user, application)
    await invites.ingest_message_invites(session, msg, _mime(_ics()))
    # 96e's thread pass will itemize like this: two rounds riding one uid.
    await rounds.upsert_round(
        session,
        application=application,
        kind="technical_screen",
        source="email",
        state="scheduled",
        scheduled_at=datetime(2026, 7, 15, 18, 0, tzinfo=UTC),
        invite_uid="uid-headway-1@google.com",
    )
    await rounds.upsert_round(
        session,
        application=application,
        kind="system_design",
        source="email",
        state="scheduled",
        scheduled_at=datetime(2026, 7, 15, 19, 0, tzinfo=UTC),
        invite_uid="uid-headway-1@google.com",
    )
    msg2 = await _make_message(session, user, application, subject="Updated invitation")
    await _ingest_and_apply(
        session, msg2, application, _ics(seq=1, start="20260715T130000", end="20260715T151500")
    )
    rows = await rounds.list_rounds(session, application_id=application.id)
    assert len(rows) == 2
    by_kind = {r.kind: r for r in rows}
    # Container moved 11:00 → 13:00 PT (+2h); both riders shift together.
    assert by_kind["technical_screen"].scheduled_at.hour == 20
    assert by_kind["system_design"].scheduled_at.hour == 21


async def test_adopts_round_the_carrying_message_already_produced(session, user, application):
    """The classify tick creates a dateless round from `extracted_round_kind`
    before invites apply — the chain must adopt it, never sibling it."""
    from services.applications import rounds
    from services.email import invites

    msg = await _make_message(session, user, application)
    existing = await rounds.upsert_round(
        session,
        application=application,
        kind="technical_screen",
        source="email",
        state="scheduled",
        email_message_id=msg.id,
    )
    await invites.ingest_message_invites(session, msg, _mime(_ics()))
    await invites.apply_invites_for_application(session, application=application)
    rows = await rounds.list_rounds(session, application_id=application.id)
    assert len(rows) == 1
    assert rows[0].id == existing.id
    assert rows[0].invite_uid == "uid-headway-1@google.com"
    assert rows[0].scheduled_at is not None


async def test_rounds_resequence_chronologically(session, user, application):
    """ "Round 1" is the interview that happens first (owner 2026-07-08),
    regardless of row-creation order; dateless rounds sort last."""
    from services.applications import rounds

    late = await rounds.upsert_round(
        session,
        application=application,
        kind="system_design",
        source="email",
        state="scheduled",
        scheduled_at=datetime(2026, 7, 20, 18, 0, tzinfo=UTC),
    )
    dateless = await rounds.upsert_round(
        session, application=application, kind="hiring_manager", source="notes", state="planned"
    )
    early = await rounds.upsert_round(
        session,
        application=application,
        kind="technical_screen",
        source="email",
        state="scheduled",
        scheduled_at=datetime(2026, 6, 26, 18, 0, tzinfo=UTC),
    )
    await rounds.resequence_rounds(session, application_id=application.id)
    rows = await rounds.list_rounds(session, application_id=application.id)
    assert [r.id for r in rows] == [early.id, late.id, dateless.id]
    assert [r.round_no for r in rows] == [1, 2, 3]


# ── Past-due completion rider ───────────────────────────────────────────


async def test_past_due_scheduled_round_completes(session, user, application):
    from services.applications import rounds

    past = await rounds.upsert_round(
        session,
        application=application,
        kind="technical_screen",
        source="email",
        state="scheduled",
        scheduled_at=datetime(2026, 7, 1, 17, 0, tzinfo=UTC),
    )
    future = await rounds.upsert_round(
        session,
        application=application,
        kind="system_design",
        source="email",
        state="scheduled",
        scheduled_at=datetime(2026, 7, 20, 17, 0, tzinfo=UTC),
    )
    n = await rounds.complete_past_due_rounds(session, now=datetime(2026, 7, 8, 12, 0, tzinfo=UTC))
    assert n == 1
    rows = {r.id: r for r in await rounds.list_rounds(session, application_id=application.id)}
    assert rows[past.id].state == "completed"
    assert rows[past.id].outcome == "pending"
    assert rows[future.id].state == "scheduled"
    # Completed onsite-evidence round drives the same forward-only stage path.
    await session.refresh(application)
    assert application.status.value == "ONSITE_LOOP"


async def test_past_due_respects_invite_end_and_grace(session, user, application):
    """The container's `ends_at` is the due clock — a round mid-container
    (or inside the 1h overrun grace) must not complete."""
    from services.applications import rounds
    from services.email import invites

    msg = await _make_message(session, user, application)
    await invites.ingest_message_invites(
        session, msg, _mime(_ics(start="20260708T090000", end="20260708T120000"))
    )
    await invites.apply_invites_for_application(session, application=application)
    # 09:00–12:00 PT = 16:00–19:00 UTC. At 18:00 UTC the container is still
    # running; at 19:30 it's inside the grace window; at 20:30 it completes.
    for probe, expected in (
        (datetime(2026, 7, 8, 18, 0, tzinfo=UTC), 0),
        (datetime(2026, 7, 8, 19, 30, tzinfo=UTC), 0),
        (datetime(2026, 7, 8, 20, 30, tzinfo=UTC), 1),
    ):
        assert await rounds.complete_past_due_rounds(session, now=probe) == expected


# ── Sync-time ingest hook (fake IMAP) ───────────────────────────────────


@pytest.fixture(autouse=True)
def _patch_imap_host_guard_dns(monkeypatch):
    import ipaddress

    from services.email import imap_host_guard

    def _fake_resolve(host: str) -> tuple[str, ...]:
        if host == "imap.example.com":
            return ("93.184.216.34",)
        try:
            ipaddress.ip_address(host)
            return (host,)
        except ValueError:
            return ()

    imap_host_guard._DNS_CACHE.clear()
    monkeypatch.setattr(imap_host_guard, "_resolve_host", _fake_resolve)
    yield
    imap_host_guard._DNS_CACHE.clear()


class _FakeIMAP:
    def __init__(self, raws: list[bytes]):
        self.raws = raws

    def login(self, user, password):
        return "OK", [b"Logged in"]

    def select(self, mailbox, readonly=False):
        return "OK", [b"INBOX selected"]

    def uid(self, command, *args):
        if command == "SEARCH":
            uids = b" ".join(str(i + 1).encode() for i in range(len(self.raws)))
            return "OK", [uids]
        if command == "FETCH":
            raw = self.raws[int(args[0]) - 1]
            return "OK", [(b"1 (BODY[] {%d}" % len(raw), raw)]
        return "NO", []

    def logout(self):
        return "OK", [b"Logged out"]


async def _make_account(session, user):
    from models import EmailAccount
    from models.enums import EmailAccountProvider
    from services.email import credentials as email_credentials

    account = EmailAccount(
        user_id=user.id,
        provider=EmailAccountProvider.IMAP,
        account_email="owner@example.com",
        imap_host="imap.example.com",
        imap_username="owner@example.com",
        imap_password="",
    )
    email_credentials.store_imap_password(account, "p@ssw0rd")
    session.add(account)
    await session.flush()
    return account


async def test_sync_ingests_invites_from_new_mail(session, user):
    from sqlmodel import select

    from models import EmailInvite
    from services.email import sync as email_sync

    account = await _make_account(session, user)
    raw = bytes(_mime(_ics()))
    result = await email_sync.sync_account(
        session, account, client_factory=lambda h, p: _FakeIMAP([raw])
    )
    assert result.new == 1
    rows = (await session.exec(select(EmailInvite))).all()
    assert len(rows) == 1
    assert rows[0].ics_uid == "uid-headway-1@google.com"
    assert rows[0].application_id is None  # unlinked until classify links


async def test_sync_survives_malformed_ics(session, user):
    from sqlmodel import select

    from models import EmailInvite, EmailMessage
    from services.email import sync as email_sync

    account = await _make_account(session, user)
    raw = bytes(_mime("BEGIN:VCALENDAR\nNOT VALID AT ALL"))
    result = await email_sync.sync_account(
        session, account, client_factory=lambda h, p: _FakeIMAP([raw])
    )
    assert result.new == 1  # the message itself still lands
    assert result.errors == []
    assert (await session.exec(select(EmailMessage))).all()
    assert (await session.exec(select(EmailInvite))).all() == []


# ── Classify-time adoption ──────────────────────────────────────────────


async def test_adopt_message_invites_stamps_application(session, user, application):
    from sqlmodel import select

    from models import EmailInvite
    from services.applications import rounds
    from services.email import invites

    msg = await _make_message(session, user, application=None)
    await invites.ingest_message_invites(session, msg, _mime(_ics()))
    row = (await session.exec(select(EmailInvite))).one()
    assert row.application_id is None

    # Linking happened (classify tick); the hook stamps + applies.
    msg.application_id = application.id
    assert await invites.adopt_message_invites(session, msg) is True
    await invites.apply_invites_for_application(session, application=application)
    row = (await session.exec(select(EmailInvite))).one()
    assert row.application_id == application.id
    assert len(await rounds.list_rounds(session, application_id=application.id)) == 1


# ── Upcoming-interviews schedule ────────────────────────────────────────


async def test_upcoming_schedule_groups_by_container(session, user, application, monkeypatch):
    from services.applications import rounds
    from services.email import invites

    msg = await _make_message(session, user, application)
    await invites.ingest_message_invites(
        session, msg, _mime(_ics(start="20260715T110000", end="20260715T141500"))
    )
    for kind, hour in (("technical_screen", 18), ("system_design", 19)):
        await rounds.upsert_round(
            session,
            application=application,
            kind=kind,
            source="email",
            state="scheduled",
            scheduled_at=datetime(2026, 7, 15, hour, 0, tzinfo=UTC),
            invite_uid="uid-headway-1@google.com",
        )
    standalone = await rounds.upsert_round(
        session,
        application=application,
        kind="hiring_manager",
        source="email",
        state="scheduled",
        scheduled_at=datetime(2026, 7, 16, 18, 0, tzinfo=UTC),
    )
    assert standalone.id is not None

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 7, 8, 12, 0, tzinfo=tz or UTC)

    monkeypatch.setattr(invites, "datetime", _FrozenDatetime)
    groups = await invites.upcoming_interview_schedule(session, user_id=user.id)
    assert len(groups) == 2
    container, single = groups
    assert len(container.entries) == 2
    assert container.company == "Headway"
    assert all(e.time_label for e in container.entries)  # segments show times
    assert len(single.entries) == 1
    assert single.entries[0].time_label is None  # singleton needs no sub-time
