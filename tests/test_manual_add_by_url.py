"""URL-first manual tracking — plan 95 § 3.7 (slice 95j).

Paste → parse (SSRF-guarded, preview only, nothing persists) → confirm at
an initial state; mid-stage creation writes the SAME back-dated trail shape
as `processes.track_process`.
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
        CompanyAlias,
        EmailAccount,
        EmailMessage,
        EmailThread,
        Job,
        SenderRule,
        Settings,
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
        CompanyAlias.__table__,
        SenderRule.__table__,
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

    u = User(email="addurl@example.com", password_hash="x", is_active=True)
    session.add(u)
    await session.flush()
    return u


_POSTING_HTML = """
<html><head><title>Senior Software Engineer | Lightfield</title></head>
<body><h1>Senior Software Engineer</h1><p>Build agentic CRM systems.</p></body></html>
"""


@pytest.fixture
def _mock_fetch(monkeypatch):
    """Mock the guard/network/LLM stages of the add-by-URL pipeline.

    The SSRF guard resolves live DNS; the canned test hosts don't resolve,
    so the guard is stubbed permissive here (its own tests cover it — and
    `test_parse_posting_rejects_unsafe_url` pins the wired-in rejection)."""
    from scraper import url_guard
    from scraper.crawl4ai_client import Crawl4AIClient

    async def _fake_fetch_html(self, url):
        return _POSTING_HTML

    monkeypatch.setattr(url_guard, "is_safe_destination", lambda url: (True, None))
    monkeypatch.setattr(Crawl4AIClient, "fetch_html", _fake_fetch_html)

    # No LLM in tests: enrich degrades via LLMProviderError inside the
    # pipeline (title-seeded fields carry the preview).
    from llm import LLMProviderError
    from services.jobs import add_by_url as abu

    def _no_provider(_settings):
        raise LLMProviderError("no key", kind="auth_required")

    import llm as llm_module

    monkeypatch.setattr(llm_module, "get_provider", _no_provider)
    return abu


async def test_parse_posting_previews_without_persisting(session, user, _mock_fetch):
    from sqlmodel import select

    from models import Job
    from services.jobs.add_by_url import parse_posting

    parsed = await parse_posting(
        session, user_id=user.id, url="https://boards.example.com/lightfield/1"
    )
    assert parsed.company == "Lightfield"
    assert parsed.role == "Senior Software Engineer"
    assert (await session.exec(select(Job))).all() == []  # preview persists NOTHING


async def test_parse_posting_rejects_unsafe_url(session, user):
    from services.jobs.add_by_url import AddByUrlError, parse_posting

    with pytest.raises(AddByUrlError):
        await parse_posting(session, user_id=user.id, url="http://169.254.169.254/latest")


async def test_parse_posting_walled_url_raises_fallback_message(session, user, monkeypatch):
    from scraper import url_guard
    from scraper.crawl4ai_client import Crawl4AIClient
    from services.jobs.add_by_url import AddByUrlError, parse_posting

    async def _empty(self, url):
        return ""

    monkeypatch.setattr(url_guard, "is_safe_destination", lambda url: (True, None))
    monkeypatch.setattr(Crawl4AIClient, "fetch_html", _empty)
    with pytest.raises(AddByUrlError, match="type the fields"):
        await parse_posting(session, user_id=user.id, url="https://walled.example.com/j/1")


async def test_mid_stage_trail_matches_track_process_shape(session, user):
    """§ 3.7 acceptance: confirm at "Interview stage" yields the same
    APPLIED → stage AppEvent trail shape track_process writes."""
    from sqlmodel import select

    from models import AppEvent, Job
    from models.enums import (
        AppEventKind,
        ApplicationBoard,
        ApplicationStatus,
        JobSource,
        StatusChangeTrigger,
    )
    from services import applications as applications_service

    job = Job(
        user_id=user.id,
        source=JobSource.MANUAL,
        board=ApplicationBoard.MANUAL,
        external_id="manual-x1",
        url="https://example.com/j/1",
        url_type="external",
        company="Lightfield",
        role="Senior Software Engineer",
        description="…",
        found_at=datetime.now(UTC),
    )
    session.add(job)
    await session.flush()

    applied_at = datetime.now(UTC) - timedelta(days=21)
    application = await applications_service.create_tracked_application(
        session,
        user_id=user.id,
        job=job,
        status=ApplicationStatus.ONSITE_LOOP,
        applied_at=applied_at,
        actor="manual_add",
        first_note="Added manually (back-filled)",
        stage_note="Stage set by you at add time",
        first_trigger=StatusChangeTrigger.MANUAL,
        stage_trigger=StatusChangeTrigger.MANUAL,
    )
    assert application.status == ApplicationStatus.ONSITE_LOOP
    assert application.applied_at == applied_at

    events = [
        e
        for e in (await session.exec(select(AppEvent))).all()
        if e.kind == AppEventKind.STATUS_CHANGE
    ]
    # Same shape as track_process: APPLIED (back-dated) then the stage hop.
    assert [e.payload["to"] for e in events] == ["APPLIED", "ONSITE_LOOP"]
    assert events[0].payload["from"] is None
    assert events[0].occurred_at.replace(tzinfo=UTC) == applied_at
    assert events[1].payload["from"] == "APPLIED"
    assert all(e.payload["is_forward"] for e in events)


async def test_track_process_still_writes_same_trail(session, user):
    """Characterization: the refactor onto the shared helper preserves the
    detected-process trail exactly (test mirrors test_email_processes)."""
    from sqlmodel import select

    from models import AppEvent, EmailMessage, EmailThread
    from models.enums import AppEventKind, ApplicationStatus, EmailClassification
    from services.email import processes

    when = datetime.now(UTC) - timedelta(days=5)
    thread = EmailThread(
        user_id=user.id,
        provider="imap",
        thread_id_external="<t-track@x>",
        subject="Interview",
        classification=EmailClassification.OTHER,
        latest_message_at=when,
    )
    session.add(thread)
    await session.flush()
    msg = EmailMessage(
        user_id=user.id,
        thread_id=thread.id,
        provider="imap",
        message_id_external="<m-track@x>",
        sender_email="r@lightfield.com",
        subject="Interview",
        snippet="…",
        received_at=when,
        classification=EmailClassification.INTERVIEW_REQUEST,
        extracted_company="Lightfield",
        extracted_stage="interview",
    )
    session.add(msg)
    await session.flush()

    application = await processes.track_process(session, user_id=user.id, company="Lightfield")
    assert application is not None
    assert application.status == ApplicationStatus.ONSITE_LOOP

    events = [
        e
        for e in (await session.exec(select(AppEvent))).all()
        if e.kind == AppEventKind.STATUS_CHANGE
    ]
    assert [e.payload["to"] for e in events] == ["APPLIED", "ONSITE_LOOP"]
    assert events[0].actor == "email_process_tracker"


# ── Route level (shim tier) ─────────────────────────────────────────────


@pytest.mark.uses_sample_data_shims
def test_parse_route_returns_preview_fragment(monkeypatch):
    from fastapi.testclient import TestClient

    from main import app
    from services.jobs import add_by_url as abu

    async def _fake_parse(session, *, user_id, url):
        return abu.ParsedPosting(
            url=url,
            company="Lightfield",
            role="Senior Software Engineer",
            location="Remote",
            description="Build agentic CRM systems.",
            salary_min=None,
            salary_max=None,
            board="manual",
        )

    monkeypatch.setattr(abu, "parse_posting", _fake_parse)
    client = TestClient(app, raise_server_exceptions=True)
    client.cookies.set("naavik_session", "fake-1")
    client.cookies.set("naavik_csrf", "x" * 48)
    r = client.post(
        "/api/v1/jobs/manual/parse",
        data={"url": "https://boards.example.com/lightfield/1"},
        headers={"X-CSRF-Token": "x" * 48},
    )
    assert r.status_code == 200
    assert 'data-testid="manual-parse-preview"' in r.text
    assert "Lightfield" in r.text
    assert 'name="stand"' in r.text  # "Where does this stand?" control
    assert "<html" not in r.text.lower()  # fragment granularity


@pytest.mark.uses_sample_data_shims
def test_parse_route_walled_url_renders_fallback(monkeypatch):
    from fastapi.testclient import TestClient

    from main import app
    from services.jobs import add_by_url as abu

    async def _fail(session, *, user_id, url):
        raise abu.AddByUrlError("Couldn't fetch the posting — type the fields instead.")

    monkeypatch.setattr(abu, "parse_posting", _fail)
    client = TestClient(app, raise_server_exceptions=True)
    client.cookies.set("naavik_session", "fake-1")
    client.cookies.set("naavik_csrf", "x" * 48)
    r = client.post(
        "/api/v1/jobs/manual/parse",
        data={"url": "https://walled.example.com/j/1"},
        headers={"X-CSRF-Token": "x" * 48},
    )
    assert r.status_code == 200
    assert 'data-testid="manual-parse-error"' in r.text
    assert "type the fields" in r.text


@pytest.mark.uses_sample_data_shims
def test_manual_modal_renders_url_first():
    from fastapi.testclient import TestClient

    from main import app

    client = TestClient(app, raise_server_exceptions=True)
    client.cookies.set("naavik_session", "fake-1")
    r = client.get("/_modal/manual-job")
    assert r.status_code == 200
    assert 'data-testid="manual-job-parse"' in r.text  # URL-first CTA
    assert 'id="manual-job-form"' in r.text  # typed fallback still present
    assert 'name="stand"' in r.text
