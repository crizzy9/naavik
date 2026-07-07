"""email_sync — IMAP fetch with a fake client (plan 90 / 0.5.0.01 Wave 9).

No live network. The `_FakeIMAP` client mocks the imaplib surface email_sync
uses (`login`, `select`, `uid("SEARCH", ...)`, `uid("FETCH", ...)`, `logout`).
"""

from __future__ import annotations

import imaplib
import os
from email.message import EmailMessage as MIMEMessage

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


def _email_test_tables():
    from sqlalchemy import CheckConstraint

    from models import (
        Application,
        EmailAccount,
        EmailMessage,
        EmailThread,
        User,
    )

    tables = [
        User.__table__,
        Application.__table__,
        EmailThread.__table__,
        EmailAccount.__table__,
        EmailMessage.__table__,
    ]
    for table in tables:
        for c in list(table.constraints):
            if isinstance(c, CheckConstraint):
                table.constraints.discard(c)
        for idx in list(table.indexes):
            if any(getattr(o, "name", None) == "deleted_at" for o in idx.columns):
                table.indexes.discard(idx)
    return tables


@pytest.fixture(autouse=True)
def _patch_imap_host_guard_dns(monkeypatch):
    """The SSRF host guard resolves real DNS at every connection point. Map the
    canned test host to a public IP (IP literals resolve to themselves) so sync
    exercises the guard without live network."""
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

    tables = _email_test_tables()
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


def _make_rfc822(
    *,
    msg_id: str = "<m1@example.com>",
    sender: str = "Recruiter <recruiter@example.com>",
    subject: str = "Interview request",
    body: str = "Hello, can we schedule a chat next week?",
) -> bytes:
    m = MIMEMessage()
    m["Message-ID"] = msg_id
    m["From"] = sender
    m["Subject"] = subject
    m["Date"] = "Mon, 23 Jun 2026 10:00:00 +0000"
    m.set_content(body)
    return bytes(m)


class _FakeIMAP:
    def __init__(self, raws: list[bytes]):
        self.raws = raws
        self.login_called = False
        self.logout_called = False
        self.select_readonly: bool | None = None
        self.fetch_commands: list[str] = []

    def login(self, user, password):
        self.login_called = True
        return "OK", [b"Logged in"]

    def select(self, mailbox, readonly=False):
        self.select_readonly = readonly
        return "OK", [b"INBOX selected"]

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
        self.logout_called = True
        return "OK", [b"Logged out"]


class _FailingFakeIMAP(_FakeIMAP):
    def login(self, user, password):
        raise imaplib.IMAP4.error("invalid credentials")


async def test_sync_account_persists_messages(session):
    from models import EmailAccount, EmailMessage, User
    from models.enums import EmailAccountProvider, EmailAccountStatus
    from services.email import credentials as email_credentials
    from services.email import sync as email_sync

    user = User(email="owner@example.com", password_hash="x", is_active=True)
    session.add(user)
    await session.flush()

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

    raws = [_make_rfc822(msg_id=f"<m{i}@example.com>", body=f"body-{i}") for i in range(3)]
    fake_client = _FakeIMAP(raws)

    def _factory(host, port):
        return fake_client

    result = await email_sync.sync_account(session, account, client_factory=_factory)
    await session.commit()

    assert fake_client.login_called
    assert fake_client.logout_called
    assert result.fetched == 3
    assert result.new == 3
    assert result.status == EmailAccountStatus.OK

    from sqlmodel import select

    msgs = (await session.exec(select(EmailMessage))).all()
    assert len(msgs) == 3
    assert all(m.user_id == user.id for m in msgs)
    assert all("body-" in m.snippet for m in msgs)
    assert all(m.classification is None for m in msgs)


async def test_sync_never_marks_mail_as_read(session):
    """Fetch must be BODY.PEEK[] and the select readonly (plan 95 § 3.6).

    A plain RFC822 fetch sets \\Seen on the owner's real mailbox — invisible
    here because fakes don't track flags, so this test pins the COMMANDS the
    client sends instead: `readonly=True` select (EXAMINE — server rejects
    all flag mutations) and `BODY.PEEK[]` (side-effect-free even read-write).
    """
    from models import EmailAccount, User
    from models.enums import EmailAccountProvider
    from services.email import credentials as email_credentials
    from services.email import sync as email_sync

    user = User(email="peek@example.com", password_hash="x", is_active=True)
    session.add(user)
    await session.flush()

    account = EmailAccount(
        user_id=user.id,
        provider=EmailAccountProvider.IMAP,
        account_email="peek@example.com",
        imap_host="imap.example.com",
        imap_username="peek@example.com",
        imap_password="",
    )
    email_credentials.store_imap_password(account, "p@ssw0rd")
    session.add(account)
    await session.flush()

    fake_client = _FakeIMAP([_make_rfc822()])
    result = await email_sync.sync_account(
        session, account, client_factory=lambda h, p: fake_client
    )
    await session.commit()

    assert result.new == 1
    assert fake_client.select_readonly is True
    assert fake_client.fetch_commands, "no FETCH issued"
    for command in fake_client.fetch_commands:
        assert "BODY.PEEK" in command
        assert "RFC822" not in command


async def test_sync_account_auth_failure_flips_status(session):
    from models import EmailAccount, User
    from models.enums import EmailAccountProvider, EmailAccountStatus
    from services.email import credentials as email_credentials
    from services.email import sync as email_sync

    user = User(email="bad@example.com", password_hash="x", is_active=True)
    session.add(user)
    await session.flush()

    account = EmailAccount(
        user_id=user.id,
        provider=EmailAccountProvider.IMAP,
        account_email="bad@example.com",
        imap_host="imap.example.com",
        imap_username="bad@example.com",
        imap_password="",
    )
    # Store a decryptable credential so the failure under test is the IMAP login
    # (not a decrypt fail-closed) — the server rejects the creds, flipping status.
    email_credentials.store_imap_password(account, "wrong-but-stored")
    session.add(account)
    await session.flush()

    failing = _FailingFakeIMAP([])

    def _factory(host, port):
        return failing

    result = await email_sync.sync_account(session, account, client_factory=_factory)
    await session.commit()
    assert result.status == EmailAccountStatus.AUTH_REQUIRED
    assert account.status == EmailAccountStatus.AUTH_REQUIRED
    assert account.connection_failure_count == 1


async def test_sync_account_dedup_on_repeat(session):
    """Re-sync same UID set without a UID cursor still de-dups via
    `uq_email_message_external` constraint."""
    from models import EmailAccount, EmailMessage, User
    from models.enums import EmailAccountProvider
    from services.email import credentials as email_credentials
    from services.email import sync as email_sync

    user = User(email="dedup@example.com", password_hash="x", is_active=True)
    session.add(user)
    await session.flush()

    account = EmailAccount(
        user_id=user.id,
        provider=EmailAccountProvider.IMAP,
        account_email="dedup@example.com",
        imap_host="imap.example.com",
        imap_username="dedup@example.com",
        imap_password="",
    )
    email_credentials.store_imap_password(account, "p@ssw0rd")
    session.add(account)
    await session.flush()

    raws = [_make_rfc822(msg_id="<dedup-1@example.com>")]
    fake_client = _FakeIMAP(raws)

    def _factory(host, port):
        return fake_client

    await email_sync.sync_account(session, account, client_factory=_factory)
    await session.commit()

    # Clear UID cursor so second pass sees the same uid range.
    account.last_synced_uid = None
    session.add(account)
    await session.flush()

    fake2 = _FakeIMAP(raws)

    def _factory2(host, port):
        return fake2

    res2 = await email_sync.sync_account(session, account, client_factory=_factory2)
    await session.commit()
    assert res2.new == 0

    from sqlmodel import select

    msgs = (await session.exec(select(EmailMessage))).all()
    assert len(msgs) == 1


async def test_sync_account_caps_untrusted_fields(session):
    """subject capped to 200, sender_email to 254 at persist (PR #214 M1/L3)."""
    from models import EmailAccount, EmailMessage, User
    from models.enums import EmailAccountProvider
    from services.email import credentials as email_credentials
    from services.email import sync as email_sync

    user = User(email="cap@example.com", password_hash="x", is_active=True)
    session.add(user)
    await session.flush()

    account = EmailAccount(
        user_id=user.id,
        provider=EmailAccountProvider.IMAP,
        account_email="cap@example.com",
        imap_host="imap.example.com",
        imap_username="cap@example.com",
        imap_password="",
    )
    email_credentials.store_imap_password(account, "p@ssw0rd")
    session.add(account)
    await session.flush()

    long_subject = "S" * 5000
    long_local = "a" * 4000
    raws = [
        _make_rfc822(
            msg_id="<cap-1@example.com>",
            sender=f"Spammy <{long_local}@evil.example.com>",
            subject=long_subject,
        )
    ]
    fake_client = _FakeIMAP(raws)

    result = await email_sync.sync_account(
        session, account, client_factory=lambda h, p: fake_client
    )
    await session.commit()
    assert result.new == 1

    from sqlmodel import select

    msg = (await session.exec(select(EmailMessage))).one()
    assert len(msg.subject) == 200
    assert len(msg.sender_email) == 254


async def test_sync_account_blocks_internal_host(session, monkeypatch):
    """A host resolving to an internal IP is rejected; account fails closed and
    the persisted error is canonical (no raw exception / IP leak)."""
    from models import EmailAccount, EmailMessage, User
    from models.enums import EmailAccountProvider, EmailAccountStatus
    from services.email import credentials as email_credentials
    from services.email import imap_host_guard
    from services.email import sync as email_sync

    # Rebind the test host to an internal IP (DNS-rebind simulation).
    monkeypatch.setattr(imap_host_guard, "_resolve_host", lambda host: ("169.254.169.254",))

    user = User(email="ssrf@example.com", password_hash="x", is_active=True)
    session.add(user)
    await session.flush()
    account = EmailAccount(
        user_id=user.id,
        provider=EmailAccountProvider.IMAP,
        account_email="ssrf@example.com",
        imap_host="imap.example.com",
        imap_username="ssrf@example.com",
        imap_password="",
    )
    email_credentials.store_imap_password(account, "p@ssw0rd")
    session.add(account)
    await session.flush()

    def _factory(host, port):
        raise AssertionError("guard must block before a client is created")

    result = await email_sync.sync_account(session, account, client_factory=_factory)
    await session.commit()

    assert result.status == EmailAccountStatus.AUTH_REQUIRED
    assert account.last_error_message == imap_host_guard.SAFE_ERROR_MESSAGE
    assert "169.254" not in (account.last_error_message or "")
    from sqlmodel import select

    assert (await session.exec(select(EmailMessage))).all() == []
