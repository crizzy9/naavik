"""PII scrubber + few-shot correction block — plan 95 § 3.4.2 (slice 95f).

The scrubber is a pure function; the few-shot builder renders owner
corrections as prompt precedents with domain-only senders. The hard
invariant: NO raw @-address in any rendered exemplar block.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles

os.environ.setdefault("NAAVIK_DEBUG", "1")

from services.email.pii_scrub import scrub  # noqa: E402


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw):  # type: ignore[misc]
    return "TEXT"


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_type, _compiler, **_kw):  # type: ignore[misc]
    return "TEXT"


# ── Scrubber (pure) ─────────────────────────────────────────────────────


def test_scrub_email_addresses():
    out = scrub("Reach me at shyam.padia930@gmail.com or hr@camber.health!")
    assert "@" not in out
    assert out.count("[email]") == 2


def test_scrub_phone_numbers():
    assert scrub("Call +1 (617) 555-0123 tomorrow") == "Call [phone] tomorrow"
    assert scrub("Cell: 617-555-0123.") == "Cell: [phone]."
    # Years / small ids survive.
    assert scrub("Since 2024 in room 12") == "Since 2024 in room 12"


def test_scrub_tokened_urls_but_keeps_bare_urls():
    out = scrub("Confirm: https://ats.example.com/confirm?token=SECRET123&uid=9")
    assert "SECRET123" not in out
    assert "[link]" in out
    kept = scrub("Posting: https://boards.greenhouse.io/stripe/jobs/1")
    assert "boards.greenhouse.io/stripe/jobs/1" in kept


def test_scrub_empty_and_none():
    assert scrub(None) == ""
    assert scrub("") == ""


# ── Few-shot builder (sqlite) ───────────────────────────────────────────


def _tables():
    from sqlalchemy import CheckConstraint

    from models import (
        Application,
        ClassificationCorrection,
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

    u = User(email="fewshot@example.com", password_hash="x", is_active=True)
    session.add(u)
    await session.flush()
    return u


async def _seed_correction(
    session,
    *,
    user_id: int,
    sender: str,
    subject: str,
    snippet: str,
    to_classification: str,
    days_ago: int = 1,
):
    from models import ClassificationCorrection, EmailMessage, EmailThread
    from models.enums import EmailClassification

    when = datetime.now(UTC) - timedelta(days=days_ago)
    thread = EmailThread(
        user_id=user_id,
        provider="imap",
        thread_id_external=f"<t-{sender}-{days_ago}-{subject[:8]}@x>",
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
        message_id_external=f"<m-{sender}-{days_ago}-{subject[:8]}@x>",
        sender_email=sender,
        subject=subject,
        snippet=snippet,
        received_at=when,
        classification=EmailClassification.FOLLOW_UP,
    )
    session.add(msg)
    await session.flush()
    session.add(
        ClassificationCorrection(
            user_id=user_id,
            message_id=msg.id,
            kind="reclassify",
            from_classification="follow_up",
            to_classification=to_classification,
            corrected_at=when,
        )
    )
    await session.flush()
    return msg


async def test_domain_match_renders_precedent_without_addresses(session, user):
    from services.email import few_shot

    await _seed_correction(
        session,
        user_id=user.id,
        sender="no-reply@bytedance.com",
        subject="Update on your application at ByteDance",
        snippet="Contact li.wei@bytedance.com — we decided to move forward with other candidates.",
        to_classification="rejection",
    )

    block = await few_shot.build_few_shot_block(
        session,
        user_id=user.id,
        sender_email="talent@bytedance.com",
        subject="Another update from ByteDance",
    )
    assert "rejection" in block
    assert "bytedance.com" in block  # domain-only sender identity
    assert "@" not in block  # NEVER a raw address (owner condition)


async def test_subject_shape_match_without_domain(session, user):
    from services.email import few_shot

    await _seed_correction(
        session,
        user_id=user.id,
        sender="no-reply@greenhouse.io",
        subject="Interview availability next steps",
        snippet="…",
        to_classification="interview_request",
    )
    block = await few_shot.build_few_shot_block(
        session,
        user_id=user.id,
        sender_email="scheduler@lever.co",  # different domain
        subject="Availability next steps for interview",  # same shape
    )
    assert "interview_request" in block


async def test_no_match_yields_empty_block(session, user):
    from services.email import few_shot

    await _seed_correction(
        session,
        user_id=user.id,
        sender="no-reply@bytedance.com",
        subject="Update on your application",
        snippet="…",
        to_classification="rejection",
    )
    block = await few_shot.build_few_shot_block(
        session,
        user_id=user.id,
        sender_email="hello@totally-different.io",
        subject="Quarterly newsletter",
    )
    assert block == ""


async def test_k_cap(session, user):
    from services.email import few_shot

    for i in range(8):
        await _seed_correction(
            session,
            user_id=user.id,
            sender="no-reply@bytedance.com",
            subject=f"Update {i} on your application",
            snippet="…",
            to_classification="rejection",
            days_ago=i + 1,
        )
    block = await few_shot.build_few_shot_block(
        session,
        user_id=user.id,
        sender_email="x@bytedance.com",
        subject="Update on your application",
    )
    assert block.count("From domain:") == few_shot.MAX_EXEMPLARS


async def test_rendered_classify_prompt_has_no_exemplar_addresses(session, user):
    """End-to-end: the block as injected into CLASSIFY_PROMPT carries no
    raw address; the incoming email's own From: line is the only @."""
    from llm.prompts.classify_email import PROMPT as CLASSIFY_PROMPT
    from services.email import few_shot

    await _seed_correction(
        session,
        user_id=user.id,
        sender="recruiter.jane@bytedance.com",
        subject="Update on your application at ByteDance",
        snippet="Write to jane.doe@bytedance.com or call 617-555-0123",
        to_classification="rejection",
    )
    block = await few_shot.build_few_shot_block(
        session,
        user_id=user.id,
        sender_email="talent@bytedance.com",
        subject="Update on your ByteDance application",
    )
    rendered = CLASSIFY_PROMPT.format(
        sender="talent@bytedance.com",
        subject="Update on your ByteDance application",
        body="snippet…",
        owner_corrections=block,
    )
    # Exactly one @ region: the incoming From: line itself.
    from_line = next(line for line in rendered.splitlines() if line.startswith("From:"))
    rest = rendered.replace(from_line, "")
    assert "@" not in rest
    assert "617-555-0123" not in rendered
