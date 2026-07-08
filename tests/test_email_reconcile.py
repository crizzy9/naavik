"""Event-driven process reconciler (plan 96 slice 96e).

The contract under test: triggered only for evidence-touched applications
(no global sweep), deterministic re-group + timeline re-fold, thread-level
LLM pass ONLY for triggering threads with unseen mail (the per-thread stamp
gates cost AND idempotence), writes ride `update_status` forward-only with
`trigger=RECONCILED`, § 3.8 pin suppression downgrades to suggestions,
CLOSED absolute, rejection stays human-confirm, and re-running with no new
evidence produces zero writes.
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
        ClassificationCorrection,
        CompanyAlias,
        EmailInvite,
        EmailMessage,
        EmailThread,
        InterviewRound,
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
        EmailMessage.__table__,
        EmailInvite.__table__,
        InterviewRound.__table__,
        CalendarEvent.__table__,
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

    u = User(email="reconcile@example.com", password_hash="x", is_active=True)
    session.add(u)
    await session.flush()
    return u


async def _make_application(session, user, *, company="Headway", status=None, artifacts=None):
    from models import Application
    from models.enums import ApplicationStatus

    a = Application(
        user_id=user.id,
        company=company,
        role="Senior Backend Software Engineer",
        status=status or ApplicationStatus.APPLIED,
        applied_at=datetime(2026, 6, 1, tzinfo=UTC),
        submission_artifacts=artifacts or {},
    )
    session.add(a)
    await session.flush()
    return a


_MSG_SEQ = iter(range(1, 10_000))


async def _make_message(
    session,
    user,
    *,
    application=None,
    thread=None,
    classification="INTERVIEW_REQUEST",
    stage=None,
    company=None,
    subject="Interview with Headway",
    received_at=None,
    body="Let's schedule your interview.",
):
    from models import EmailMessage, EmailThread
    from models.enums import EmailClassification

    n = next(_MSG_SEQ)
    cls = EmailClassification[classification] if classification else None
    if thread is None:
        thread = EmailThread(
            user_id=user.id,
            provider="imap",
            thread_id_external=f"<t{n}@x>",
            subject=subject,
            classification=cls or EmailClassification.OTHER,
            latest_message_at=received_at or datetime(2026, 7, 7, tzinfo=UTC),
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
        message_id_external=f"<m{n}@x>",
        sender_email="recruit@headway.co",
        subject=subject,
        snippet=body[:240],
        body_excerpt=body,
        received_at=received_at or datetime(2026, 7, 7, tzinfo=UTC),
        classification=cls,
        extracted_stage=stage,
        extracted_company=company,
    )
    session.add(msg)
    await session.flush()
    return msg, thread


def _fake_llm(monkeypatch, results: list[dict]):
    """Patch settings/provider/tracked_call on the reconcile module; returns
    the list of rendered prompts (one per LLM call)."""
    from services.email import reconcile

    calls: list[str] = []

    async def _fake_settings(_session, *, user_id):
        return object()

    class _Provider:
        model = "fake-model"

    async def _fake_tracked_call(**kwargs):
        calls.append(kwargs.get("prompt") or "")
        if not results:
            raise AssertionError("unexpected extra LLM call")
        return type("R", (), {"value": results.pop(0)})()

    monkeypatch.setattr(reconcile, "_get_settings", _fake_settings)
    monkeypatch.setattr(reconcile, "get_provider", lambda _s: _Provider())
    monkeypatch.setattr(reconcile.llm_tracker, "tracked_call", _fake_tracked_call)
    return calls


_NO_OP_THREAD_RESULT = {
    "process_stage": None,
    "rounds": [],
    "rejection": False,
    "needs_scheduling": False,
}


# ── Deterministic core ──────────────────────────────────────────────────


async def test_regroup_links_stray_rejection_and_suggests_closed(session, user):
    """The "rejection landed in a different group" class: an unlinked
    REJECTION whose extracted company canonicalizes to this application gets
    linked, and CLOSED stays a human-confirm suggestion."""
    from models.enums import ApplicationStatus
    from services.email import reconcile

    app = await _make_application(session, user, status=ApplicationStatus.ONSITE_LOOP)
    stray, _ = await _make_message(
        session,
        user,
        classification="REJECTION",
        company="Headway Inc.",
        subject="Your application to Headway",
    )
    result = await reconcile.reconcile_application(session, application_id=app.id)
    assert result is not None
    assert result.relinked_messages == 1
    await session.refresh(stray)
    assert stray.application_id == app.id
    await session.refresh(app)
    assert app.status == ApplicationStatus.ONSITE_LOOP  # never auto-closed
    assert stray.suggested_status == ApplicationStatus.CLOSED
    assert result.status_suggested is True


async def test_regroup_never_readopts_humanly_unlinked_threads(session, user):
    """§ 3.8 — human intent outranks machine inference: a thread the human
    unlinked must not be re-adopted by company match on the next reconcile
    (the unlink correction is the durable objection)."""
    from models import ClassificationCorrection
    from models.enums import ApplicationStatus
    from services.email import reconcile

    app = await _make_application(session, user, status=ApplicationStatus.ONSITE_LOOP)
    stray, thread = await _make_message(
        session, user, classification="INTERVIEW_REQUEST", company="Headway"
    )
    session.add(
        ClassificationCorrection(
            user_id=user.id,
            message_id=stray.id,
            kind="unlink",
            from_company="Headway",
            to_company=None,
        )
    )
    await session.flush()
    result = await reconcile.reconcile_application(session, application_id=app.id)
    assert result.relinked_messages == 0
    await session.refresh(stray)
    assert stray.application_id is None
    await session.refresh(thread)
    assert thread.application_id is None


async def test_forward_move_carries_reconciled_trigger(session, user):
    from sqlmodel import select

    from models import AppEvent
    from models.enums import AppEventKind, ApplicationStatus
    from services.email import reconcile

    app = await _make_application(session, user, status=ApplicationStatus.APPLIED)
    await _make_message(
        session, user, application=app, classification="INTERVIEW_REQUEST", stage="interview"
    )
    result = await reconcile.reconcile_application(session, application_id=app.id)
    assert result.status_moved is True
    await session.refresh(app)
    assert app.status == ApplicationStatus.ONSITE_LOOP
    events = (
        await session.exec(select(AppEvent).where(AppEvent.kind == AppEventKind.STATUS_CHANGE))
    ).all()
    assert any(e.payload.get("trigger") == "reconciled" for e in events)


async def test_pin_suppression_downgrades_to_suggestion(session, user):
    from sqlmodel import select

    from models import AppEvent
    from models.enums import AppEventKind, ApplicationStatus
    from services.email import reconcile

    app = await _make_application(
        session,
        user,
        status=ApplicationStatus.APPLIED,
        artifacts={"status_pin": {"rejected": "ONSITE_LOOP", "at": "2026-07-01T00:00:00+00:00"}},
    )
    msg, _ = await _make_message(
        session, user, application=app, classification="INTERVIEW_REQUEST", stage="interview"
    )
    result = await reconcile.reconcile_application(session, application_id=app.id)
    await session.refresh(app)
    assert app.status == ApplicationStatus.APPLIED  # rule 2 — pin holds
    assert result.status_suggested is True
    await session.refresh(msg)
    assert msg.suggested_status == ApplicationStatus.ONSITE_LOOP
    suggested = (
        await session.exec(
            select(AppEvent).where(AppEvent.kind == AppEventKind.EMAIL_STATUS_SUGGESTED)
        )
    ).all()
    assert any(e.payload.get("suppressed_by_pin") for e in suggested)  # rule 5


async def test_closed_is_absolute(session, user):
    from models.enums import ApplicationStatus
    from services.email import reconcile

    app = await _make_application(session, user, status=ApplicationStatus.CLOSED)
    await _make_message(
        session, user, application=app, classification="INTERVIEW_REQUEST", stage="interview"
    )
    result = await reconcile.reconcile_application(session, application_id=app.id)
    await session.refresh(app)
    assert app.status == ApplicationStatus.CLOSED
    assert result.status_moved is False


async def test_other_mail_never_evidences_a_stage(session, user):
    from models.enums import ApplicationStatus
    from services.email import reconcile

    app = await _make_application(session, user, status=ApplicationStatus.DRAFT)
    await _make_message(session, user, application=app, classification="OTHER")
    await reconcile.reconcile_application(session, application_id=app.id)
    await session.refresh(app)
    assert app.status == ApplicationStatus.DRAFT


async def test_zero_evidence_never_moves(session, user):
    from models.enums import ApplicationStatus
    from services.email import reconcile

    app = await _make_application(session, user, status=ApplicationStatus.DRAFT)
    result = await reconcile.reconcile_application(session, application_id=app.id)
    await session.refresh(app)
    assert app.status == ApplicationStatus.DRAFT
    assert result.status_moved is False


# ── Thread-level LLM pass ───────────────────────────────────────────────


async def test_application_pass_gated_by_triggering_threads(session, user, monkeypatch):
    """ONE application-level call renders ALL signal conversations (the
    canonical read needs full context) but fires only when a TRIGGERING
    thread carries unseen mail."""
    from models.enums import ApplicationStatus
    from services.email import reconcile

    app = await _make_application(session, user, status=ApplicationStatus.ONSITE_LOOP)
    _, t1 = await _make_message(
        session, user, application=app, subject="Thread ONE — schedule your onsite"
    )
    await _make_message(session, user, application=app, subject="Thread TWO — older chatter")
    calls = _fake_llm(monkeypatch, [dict(_NO_OP_THREAD_RESULT)])
    result = await reconcile.reconcile_application(
        session, application_id=app.id, triggering_thread_ids={t1.id}
    )
    assert result.thread_passes == 1
    assert len(calls) == 1
    assert "Thread ONE" in calls[0]
    assert "Thread TWO" in calls[0]  # full context, one call

    # A non-triggering reconcile (deterministic-only) makes no LLM calls.
    result2 = await reconcile.reconcile_application(session, application_id=app.id)
    assert result2.thread_passes == 0
    assert len(calls) == 1


async def test_thread_pass_stamp_gates_reruns(session, user, monkeypatch):
    """Idempotence: a second reconcile with the same triggering thread and no
    new mail makes ZERO LLM calls and zero writes."""
    from sqlmodel import select

    from models import AppEvent, InterviewRound
    from models.enums import ApplicationStatus
    from services.email import reconcile

    app = await _make_application(session, user, status=ApplicationStatus.ONSITE_LOOP)
    _, t1 = await _make_message(session, user, application=app)
    _fake_llm(
        monkeypatch,
        [
            {
                "process_stage": "interview",
                "rounds": [{"kind": "technical_screen", "title": "Coding", "state": "planned"}],
                "rejection": False,
                "needs_scheduling": False,
            }
        ],
    )
    await reconcile.reconcile_application(
        session, application_id=app.id, triggering_thread_ids={t1.id}
    )
    rounds = (await session.exec(select(InterviewRound))).all()
    assert len(rounds) == 1
    snapshot = (rounds[0].kind, rounds[0].state, rounds[0].updated_at)
    events_before = len((await session.exec(select(AppEvent))).all())

    # Second run: the fake LLM would raise on any extra call (results empty).
    result2 = await reconcile.reconcile_application(
        session, application_id=app.id, triggering_thread_ids={t1.id}
    )
    assert result2.thread_passes == 0
    rounds2 = (await session.exec(select(InterviewRound))).all()
    assert len(rounds2) == 1
    assert (rounds2[0].kind, rounds2[0].state, rounds2[0].updated_at) == snapshot
    assert len((await session.exec(select(AppEvent))).all()) == events_before


async def test_thread_pass_itemizes_container_rounds_in_place(session, user, monkeypatch):
    """Owner 2026-07-08: the 96d generic container round is REWRITTEN into
    the first derived interview; siblings ride the same calendar event."""
    from models import EmailInvite
    from models.enums import ApplicationStatus
    from services.applications import rounds as rounds_service
    from services.email import reconcile

    app = await _make_application(session, user, status=ApplicationStatus.ONSITE_LOOP)
    msg, t1 = await _make_message(session, user, application=app)
    session.add(
        EmailInvite(
            user_id=user.id,
            email_message_id=msg.id,
            application_id=app.id,
            ics_uid="uid-loop@google.com",
            method="request",
            status="confirmed",
            starts_at=datetime(2026, 7, 13, 18, 0, tzinfo=UTC),
            ends_at=datetime(2026, 7, 13, 21, 45, tzinfo=UTC),
            tz="America/New_York",
        )
    )
    await session.flush()
    generic = await rounds_service.upsert_round(
        session,
        application=app,
        kind="other",
        source="email",
        state="scheduled",
        scheduled_at=datetime(2026, 7, 13, 18, 0, tzinfo=UTC),
        invite_uid="uid-loop@google.com",
    )
    _fake_llm(
        monkeypatch,
        [
            {
                "process_stage": "interview",
                "rounds": [
                    {
                        "kind": "technical_screen",
                        "title": "Coding",
                        "interviewer": "Alex Chen",
                        "date": "2026-07-13",
                        "time": "14:00",
                        "state": "scheduled",
                    },
                    {
                        "kind": "system_design",
                        "title": "Systems Design",
                        "interviewer": "Leon Ma",
                        "date": "2026-07-13",
                        "time": "15:00",
                        "state": "scheduled",
                    },
                ],
                "rejection": False,
                "needs_scheduling": False,
            }
        ],
    )
    await reconcile.reconcile_application(
        session, application_id=app.id, triggering_thread_ids={t1.id}
    )
    rows = await rounds_service.list_rounds(session, application_id=app.id)
    assert len(rows) == 2  # rewrite + one sibling; never a third
    by_kind = {r.kind: r for r in rows}
    assert set(by_kind) == {"technical_screen", "system_design"}
    assert by_kind["technical_screen"].id == generic.id  # adopted in place
    assert all(r.invite_uid == "uid-loop@google.com" for r in rows)
    # 14:00 America/New_York (the container's tz) → 18:00 UTC.
    assert by_kind["technical_screen"].scheduled_at.hour == 18
    assert by_kind["system_design"].scheduled_at.hour == 19
    assert "Alex Chen" in (by_kind["technical_screen"].title or "")


async def test_thread_pass_rejection_suggests_closed(session, user, monkeypatch):
    from models.enums import ApplicationStatus
    from services.email import reconcile

    app = await _make_application(session, user, status=ApplicationStatus.ONSITE_LOOP)
    msg, t1 = await _make_message(
        session, user, application=app, classification="FOLLOW_UP", subject="Update on your process"
    )
    _fake_llm(
        monkeypatch,
        [dict(_NO_OP_THREAD_RESULT, rejection=True)],
    )
    result = await reconcile.reconcile_application(
        session, application_id=app.id, triggering_thread_ids={t1.id}
    )
    await session.refresh(app)
    assert app.status == ApplicationStatus.ONSITE_LOOP  # human-confirm
    assert result.status_suggested is True
    await session.refresh(msg)
    assert msg.suggested_status == ApplicationStatus.CLOSED


async def test_needs_scheduling_stamped_in_jsonb_slot(session, user, monkeypatch):
    from models.enums import ApplicationStatus
    from services.email import reconcile

    app = await _make_application(session, user, status=ApplicationStatus.ONSITE_LOOP)
    _, t1 = await _make_message(
        session, user, application=app, subject="Please send your availability"
    )
    _fake_llm(monkeypatch, [dict(_NO_OP_THREAD_RESULT, needs_scheduling=True)])
    result = await reconcile.reconcile_application(
        session, application_id=app.id, triggering_thread_ids={t1.id}
    )
    assert result.needs_scheduling is True
    await session.refresh(app)
    slot = (app.submission_artifacts or {}).get("reconcile", {})
    assert slot.get("needs_scheduling", {}).get("thread_id") == t1.id


async def test_llm_failure_degrades_to_deterministic_core(session, user, monkeypatch):
    from services.email import reconcile

    app = await _make_application(session, user)
    _, t1 = await _make_message(session, user, application=app)
    stray, _ = await _make_message(
        session, user, classification="FOLLOW_UP", company="Headway", subject="Receipt"
    )

    async def _boom(**_kw):
        raise RuntimeError("provider melted")

    async def _fake_settings(_session, *, user_id):
        return object()

    monkeypatch.setattr(reconcile, "_get_settings", _fake_settings)
    monkeypatch.setattr(reconcile, "get_provider", lambda _s: object())
    monkeypatch.setattr(reconcile.llm_tracker, "tracked_call", _boom)

    result = await reconcile.reconcile_application(
        session, application_id=app.id, triggering_thread_ids={t1.id}
    )
    assert result is not None
    assert result.thread_passes == 0
    await session.refresh(stray)
    assert stray.application_id == app.id  # the core still ran


# ── Trigger wiring ──────────────────────────────────────────────────────


async def test_classify_tick_reconciles_once_per_application(session, user, monkeypatch):
    """Batch-dedup: three new messages across two threads of ONE application
    → exactly one reconcile, scoped to those two threads."""
    from services.email import classifier as email_classifier
    from services.email import reconcile as reconcile_service

    app = await _make_application(session, user)
    m1, t1 = await _make_message(session, user, application=app, classification=None)
    m2, _ = await _make_message(session, user, application=app, thread=t1, classification=None)
    m3, t2 = await _make_message(session, user, application=app, classification=None)

    async def _fake_settings(_session, *, user_id):
        return object()

    class _Provider:
        model = "fake"

    async def _fake_tracked_call(**_kw):
        return type(
            "R",
            (),
            {
                "value": {
                    "classification": "follow_up",
                    "urgency": "low",
                    "company": "Headway",
                }
            },
        )()

    calls: list[tuple[int, frozenset]] = []

    async def _fake_reconcile(_session, *, application_id, triggering_thread_ids=None):
        calls.append((application_id, frozenset(triggering_thread_ids or ())))

    monkeypatch.setattr(email_classifier, "_get_settings", _fake_settings)
    monkeypatch.setattr(email_classifier, "get_provider", lambda _s: _Provider())
    monkeypatch.setattr(email_classifier.llm_tracker, "tracked_call", _fake_tracked_call)
    monkeypatch.setattr(reconcile_service, "reconcile_application", _fake_reconcile)

    n = await email_classifier.classify_unprocessed(session, limit=50)
    assert n == 3
    assert len(calls) == 1
    app_id, thread_ids = calls[0]
    assert app_id == app.id
    assert thread_ids == frozenset({t1.id, t2.id})


async def test_reconcile_group_delegates_when_application_exists(session, user, monkeypatch):
    from services.email import reconcile

    app = await _make_application(session, user, company="Headway")

    seen = []

    async def _fake_reconcile(_session, *, application_id, triggering_thread_ids=None):
        seen.append(application_id)
        return None

    monkeypatch.setattr(reconcile, "reconcile_application", _fake_reconcile)
    await reconcile.reconcile_group(session, user_id=user.id, company="Headway Inc")
    assert seen == [app.id]

    assert await reconcile.reconcile_group(session, user_id=user.id, company="Nonexistent") is None
