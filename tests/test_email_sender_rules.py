"""Sender rules + agency parking — plan 95 § 3.3 (slice 95c).

Precedence: user `SenderRule` > deterministic seed > LLM `sender_type` guess.
Agency mail with no named end-client parks (collapsed group, fully silent);
a named end-client evidences a real process at that company.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

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

    u = User(email="rules@example.com", password_hash="x", is_active=True)
    session.add(u)
    await session.flush()
    return u


async def _seed_unclassified(
    session,
    *,
    user_id: int,
    sender: str,
    subject: str = "Opportunity",
    snippet: str = "…",
    offset_days: int = 0,
):
    from models import EmailMessage, EmailThread
    from models.enums import EmailClassification

    when = datetime.now(UTC) - timedelta(days=offset_days)
    thread = EmailThread(
        user_id=user_id,
        provider="imap",
        thread_id_external=f"<t-{sender}-{offset_days}-{subject[:10]}@x>",
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
        message_id_external=f"<m-{sender}-{offset_days}-{subject[:10]}@x>",
        sender_email=sender,
        subject=subject,
        snippet=snippet,
        received_at=when,
    )
    session.add(msg)
    await session.flush()
    return msg


def _classifier_fakes(monkeypatch, llm_result: dict):
    from services.email import classifier as email_classifier

    class _FakeProvider:
        model = "stub"

    class _FakeStructured:
        def __init__(self, value):
            self.value = value

    async def _fake_get_settings(_session, *, user_id):
        return SimpleNamespace(user_id=user_id)

    async def _fake_tracked_call(**kwargs):
        return _FakeStructured(dict(llm_result))

    notify_calls: list = []

    async def _fake_notify(**kwargs):
        notify_calls.append(kwargs)

    monkeypatch.setattr(email_classifier, "_get_settings", _fake_get_settings)
    monkeypatch.setattr(email_classifier, "get_provider", lambda _s: _FakeProvider())
    monkeypatch.setattr(email_classifier.llm_tracker, "tracked_call", _fake_tracked_call)
    monkeypatch.setattr(email_classifier.notify, "notify_priority_email", _fake_notify)
    return notify_calls


# ── treatment precedence ────────────────────────────────────────────────


def test_treatment_precedence_user_rule_beats_seed():
    from models import SenderRule
    from services.email import sender_rules

    # Seed says g2i.co is an agency…
    assert sender_rules.treatment_for([], sender_email="talent@g2i.co") == "agency"
    # …but the user flagged it "actually an employer": user rule wins.
    rule = SenderRule(user_id=1, matcher="domain", value="g2i.co", treatment="employer")
    assert sender_rules.treatment_for([rule], sender_email="talent@g2i.co") == "employer"
    # Subdomains match the rule too.
    assert sender_rules.treatment_for([rule], sender_email="x@mail.g2i.co") == "employer"


def test_treatment_company_key_rule():
    from models import SenderRule
    from services.email import sender_rules

    rule = SenderRule(user_id=1, matcher="company_key", value="triedge", treatment="agency")
    assert (
        sender_rules.treatment_for([rule], sender_email="a@gmail.com", company="TriEdge Inc")
        == "agency"
    )
    assert sender_rules.treatment_for([rule], sender_email="a@gmail.com", company="Ripple") is None


# ── classifier: extraction + parking ────────────────────────────────────


async def test_agency_mail_parks_not_detects(session, user, monkeypatch):
    """G2i-style agency mail with no end-client: parked group, no detected
    process, no application link, ZERO notifications."""
    from services.email import classifier as email_classifier
    from services.email import processes

    notify_calls = _classifier_fakes(
        monkeypatch,
        {
            "classification": "assessment",
            "urgency": "medium",
            "company": "G2i",
            "sender_type": "agency_recruiter",
            "end_client": None,
        },
    )
    msg = await _seed_unclassified(
        session,
        user_id=user.id,
        sender="assessments@g2i.co",
        subject="Your G2i assessment",
    )
    await email_classifier.classify_unprocessed(session)

    assert msg.extracted_sender_type == "agency_recruiter"
    assert msg.application_id is None
    assert await processes.list_detected_processes(session, user_id=user.id) == []
    parked = await processes.list_parked_sender_groups(session, user_id=user.id)
    assert len(parked) == 1
    assert parked[0].sender_domain == "g2i.co"
    assert notify_calls == []  # parked mail is fully silent


async def test_agency_mail_with_end_client_detects_at_end_client(session, user, monkeypatch):
    """Camo People coordinating a Ripple interview → the process is at
    Ripple, keyed on the END-CLIENT, not the agency."""
    from services.email import classifier as email_classifier
    from services.email import processes

    _classifier_fakes(
        monkeypatch,
        {
            "classification": "interview_request",
            "urgency": "high",
            "company": "Camo People",
            "stage": "interview",
            "sender_type": "agency_recruiter",
            "end_client": "Ripple",
        },
    )
    await _seed_unclassified(
        session,
        user_id=user.id,
        sender="coach@camopeople.com",
        subject="Prep for your Ripple interview",
        snippet="Your Ripple system design round is Thursday.",
    )
    await email_classifier.classify_unprocessed(session)

    detected = await processes.list_detected_processes(session, user_id=user.id)
    assert len(detected) == 1
    assert detected[0].company == "Ripple"
    assert await processes.list_parked_sender_groups(session, user_id=user.id) == []


async def test_end_client_must_appear_verbatim(session, user, monkeypatch):
    """An invented end-client (not in subject/snippet) is dropped — the
    deterministic post-check beats model confabulation."""
    from services.email import classifier as email_classifier

    _classifier_fakes(
        monkeypatch,
        {
            "classification": "interview_request",
            "urgency": "medium",
            "company": "G2i",
            "sender_type": "agency_recruiter",
            "end_client": "Netflix",  # never mentioned in the email text
        },
    )
    msg = await _seed_unclassified(
        session,
        user_id=user.id,
        sender="talent@g2i.co",
        subject="Next steps with your match",
        snippet="A client is interested in your profile.",
    )
    await email_classifier.classify_unprocessed(session)
    assert msg.extracted_end_client is None


async def test_seed_overrides_llm_employer_guess(session, user, monkeypatch):
    """RiseSmart mail the LLM calls 'employer' still parks — deterministic
    seed outranks the model guess."""
    from services.email import classifier as email_classifier
    from services.email import processes

    _classifier_fakes(
        monkeypatch,
        {
            "classification": "interview_request",
            "urgency": "medium",
            "company": "RiseSmart",
            "sender_type": "employer",  # wrong guess
            "end_client": None,
        },
    )
    msg = await _seed_unclassified(
        session,
        user_id=user.id,
        sender="coach@risesmart.com",
        subject="Your career transition session",
    )
    await email_classifier.classify_unprocessed(session)

    assert msg.extracted_sender_type == "agency_recruiter"
    assert await processes.list_detected_processes(session, user_id=user.id) == []
    assert len(await processes.list_parked_sender_groups(session, user_id=user.id)) == 1


async def test_pre_95c_seed_domain_mail_parks_at_read_time(session, user):
    """Mail classified BEFORE the sender_type column existed (extracted
    sender type NULL) from a seed domain still parks — the rule/seed layers
    apply at read time, not only at classify time."""
    from models.enums import EmailClassification
    from services.email import processes

    msg = await _seed_unclassified(
        session, user_id=user.id, sender="talent@g2i.co", subject="Assessment invite"
    )
    msg.classification = EmailClassification.ASSESSMENT
    msg.extracted_company = "G2i"
    msg.extracted_sender_type = None  # pre-95c row
    session.add(msg)
    await session.flush()

    assert await processes.list_detected_processes(session, user_id=user.id) == []
    parked = await processes.list_parked_sender_groups(session, user_id=user.id)
    assert len(parked) == 1 and parked[0].sender_domain == "g2i.co"


# ── flag_sender (retroactive) ───────────────────────────────────────────


async def test_flag_sender_agency_retroactively_parks(session, user):
    from sqlmodel import select

    from models import ClassificationCorrection, SenderRule
    from models.enums import EmailClassification
    from services.email import processes, sender_rules

    msg = await _seed_unclassified(
        session,
        user_id=user.id,
        sender="recruiter@triedge.in",
        subject="Exciting SWE opportunity",
    )
    msg.classification = EmailClassification.INTERVIEW_REQUEST
    msg.extracted_company = "TriEdge Investments"
    msg.classification_at = datetime.now(UTC)
    session.add(msg)
    await session.flush()
    assert len(await processes.list_detected_processes(session, user_id=user.id)) == 1

    n = await sender_rules.flag_sender(
        session, user_id=user.id, domain="triedge.in", treatment="agency"
    )
    assert n == 1
    assert msg.extracted_sender_type == "agency_recruiter"
    assert await processes.list_detected_processes(session, user_id=user.id) == []
    assert len(await processes.list_parked_sender_groups(session, user_id=user.id)) == 1

    rule = (await session.exec(select(SenderRule))).one()
    assert (rule.matcher, rule.value, rule.treatment) == ("domain", "triedge.in", "agency")
    correction = (await session.exec(select(ClassificationCorrection))).one()
    assert correction.kind == "flag_sender"


async def test_flag_sender_ignore_clears_group_entirely(session, user):
    from models.enums import EmailClassification
    from services.email import processes, sender_rules

    msg = await _seed_unclassified(
        session, user_id=user.id, sender="promo@jobspam.io", subject="1000 jobs for you"
    )
    msg.classification = EmailClassification.INTERVIEW_REQUEST  # misclassified
    msg.extracted_company = "Jobspam"
    session.add(msg)
    await session.flush()

    await sender_rules.flag_sender(
        session, user_id=user.id, domain="jobspam.io", treatment="ignore"
    )
    assert msg.classification == EmailClassification.OTHER
    assert msg.extracted_company is None
    assert await processes.list_detected_processes(session, user_id=user.id) == []
    assert await processes.list_parked_sender_groups(session, user_id=user.id) == []


async def test_flag_sender_rejects_garbage_domain(session, user):
    from services.email import sender_rules

    with pytest.raises(sender_rules.SenderRuleError):
        await sender_rules.flag_sender(
            session, user_id=user.id, domain="not a domain", treatment="agency"
        )
    with pytest.raises(sender_rules.SenderRuleError):
        await sender_rules.flag_sender(
            session, user_id=user.id, domain="g2i.co", treatment="banhammer"
        )


# ── route pin: CSRF ─────────────────────────────────────────────────────


@pytest.mark.uses_sample_data_shims
def test_flag_route_requires_csrf():
    from fastapi.testclient import TestClient

    from main import app

    client = TestClient(app, raise_server_exceptions=True)
    client.cookies.set("naavik_session", "fake-1")
    resp = client.post(
        "/api/v1/email/senders/flag", data={"domain": "g2i.co", "treatment": "agency"}
    )
    assert resp.status_code == 403
