"""Full-body handling — plan 95 § 3.9.1 (slice 95l).

UID always persisted; 2k excerpt only with the per-account opt-in; the
on-demand body fetch PEEKs live and never stores; the classifier prefers
the excerpt over the snippet.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from email.message import EmailMessage as MIMEMessage
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles

os.environ.setdefault("NAAVIK_DEBUG", "1")


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
        SenderRule,
        User,
    )

    tables = [
        User.__table__,
        Application.__table__,
        AppEvent.__table__,
        EmailThread.__table__,
        EmailAccount.__table__,
        EmailMessage.__table__,
        CompanyAlias.__table__,
        SenderRule.__table__,
    ]
    for table in tables:
        for c in list(table.constraints):
            if isinstance(c, CheckConstraint):
                table.constraints.discard(c)
    return tables


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


_LONG_BODY = "This is the full body of the interview email. " * 30  # ~1400 chars


def _make_rfc822(msg_id: str = "<b1@example.com>", body: str = _LONG_BODY) -> bytes:
    m = MIMEMessage()
    m["Message-ID"] = msg_id
    m["From"] = "Recruiter <recruiter@example.com>"
    m["Subject"] = "Interview request"
    m["Date"] = "Mon, 23 Jun 2026 10:00:00 +0000"
    m.set_content(body)
    return bytes(m)


class _FakeIMAP:
    def __init__(self, raws: list[bytes]):
        self.raws = raws
        self.select_readonly: bool | None = None
        self.fetch_commands: list[str] = []

    def login(self, user, password):
        return "OK", [b"ok"]

    def select(self, mailbox, readonly=False):
        self.select_readonly = readonly
        return "OK", [b"ok"]

    def uid(self, command, *args):
        if command == "SEARCH":
            uids = b" ".join(str(i + 1).encode() for i in range(len(self.raws)))
            return "OK", [uids]
        if command == "FETCH":
            uid = args[0]
            self.fetch_commands.append(" ".join(str(a) for a in args[1:]))
            raw = self.raws[int(uid) - 1]
            return "OK", [(b"1 (BODY[] {%d}" % len(raw), raw)]
        return "NO", []

    def logout(self):
        return "OK", [b"bye"]


async def _seed_account(session, *, store_excerpt: bool):
    from models import EmailAccount, User
    from models.enums import EmailAccountProvider
    from services.email import credentials as email_credentials

    user = User(email=f"body-{store_excerpt}@example.com", password_hash="x", is_active=True)
    session.add(user)
    await session.flush()
    account = EmailAccount(
        user_id=user.id,
        provider=EmailAccountProvider.IMAP,
        account_email=user.email,
        imap_host="imap.example.com",
        imap_username=user.email,
        imap_password="",
        store_body_excerpt=store_excerpt,
    )
    email_credentials.store_imap_password(account, "p@ssw0rd")
    session.add(account)
    await session.flush()
    return user, account


async def test_sync_stores_uid_always_and_excerpt_only_when_opted(session):
    from sqlmodel import select

    from models import EmailMessage
    from services.email import sync as email_sync

    user, account = await _seed_account(session, store_excerpt=False)
    fake = _FakeIMAP([_make_rfc822()])
    await email_sync.sync_account(session, account, client_factory=lambda h, p: fake)
    msg = (await session.exec(select(EmailMessage))).one()
    assert msg.imap_uid == "1"  # UID always
    assert msg.body_excerpt is None  # default posture unchanged
    assert len(msg.snippet) <= 240

    account.store_body_excerpt = True
    account.last_synced_uid = None
    session.add(account)
    await session.flush()
    fake2 = _FakeIMAP([_make_rfc822(msg_id="<b2@example.com>")])
    await email_sync.sync_account(session, account, client_factory=lambda h, p: fake2)
    msgs = (await session.exec(select(EmailMessage).order_by(EmailMessage.id))).all()
    assert msgs[-1].body_excerpt is not None
    assert len(msgs[-1].body_excerpt) <= 2000
    assert len(msgs[-1].body_excerpt) > 240  # real lever over the snippet


async def test_fetch_message_body_peeks_and_never_persists(session):
    from sqlmodel import select

    from models import EmailMessage
    from services.email import sync as email_sync

    user, account = await _seed_account(session, store_excerpt=False)
    fake = _FakeIMAP([_make_rfc822()])
    await email_sync.sync_account(session, account, client_factory=lambda h, p: fake)
    msg = (await session.exec(select(EmailMessage))).one()

    reader = _FakeIMAP([_make_rfc822()])
    body = await email_sync.fetch_message_body(
        account, uid=msg.imap_uid, client_factory=lambda h, p: reader
    )
    assert body is not None
    assert "full body of the interview email" in body
    # PEEK + readonly on the read path too — reading must not mark read.
    assert reader.select_readonly is True
    assert all("BODY.PEEK" in c for c in reader.fetch_commands)
    # Never persisted.
    await session.refresh(msg)
    assert msg.body_excerpt is None


async def test_classifier_prefers_body_excerpt(session, monkeypatch):
    from models import EmailMessage, EmailThread, User
    from models.enums import EmailClassification
    from services.email import classifier as email_classifier

    user = User(email="ctx@example.com", password_hash="x", is_active=True)
    session.add(user)
    await session.flush()
    thread = EmailThread(
        user_id=user.id,
        provider="imap",
        thread_id_external="<t-ctx@x>",
        subject="s",
        classification=EmailClassification.OTHER,
        latest_message_at=datetime.now(UTC),
    )
    session.add(thread)
    await session.flush()
    msg = EmailMessage(
        user_id=user.id,
        thread_id=thread.id,
        provider="imap",
        message_id_external="<m-ctx@x>",
        sender_email="r@x.com",
        subject="s",
        snippet="SHORT-SNIPPET",
        body_excerpt="LONG-EXCERPT with much more classifier context",
        received_at=datetime.now(UTC),
    )
    session.add(msg)
    await session.flush()

    captured: dict[str, str] = {}

    class _FakeProvider:
        model = "stub"

    class _FakeStructured:
        def __init__(self, value):
            self.value = value

    async def _fake_get_settings(_session, *, user_id):
        return SimpleNamespace(user_id=user_id)

    async def _fake_tracked_call(**kwargs):
        captured["prompt"] = kwargs["prompt"]
        return _FakeStructured({"classification": "other"})

    monkeypatch.setattr(email_classifier, "_get_settings", _fake_get_settings)
    monkeypatch.setattr(email_classifier, "get_provider", lambda _s: _FakeProvider())
    monkeypatch.setattr(email_classifier.llm_tracker, "tracked_call", _fake_tracked_call)

    await email_classifier.classify_unprocessed(session)
    assert "LONG-EXCERPT" in captured["prompt"]
    assert "SHORT-SNIPPET" not in captured["prompt"]


# ── Route pins ──────────────────────────────────────────────────────────


@pytest.mark.uses_sample_data_shims
@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/api/v1/email/messages/1/body", {}),
        ("/api/v1/integrations/email/1/body-excerpt", {"enabled": "1"}),
    ],
)
def test_body_routes_require_csrf(path: str, body: dict):
    from fastapi.testclient import TestClient

    from main import app

    client = TestClient(app, raise_server_exceptions=True)
    client.cookies.set("naavik_session", "fake-1")  # authed, no CSRF pair
    resp = client.post(path, data=body)
    assert resp.status_code == 403
