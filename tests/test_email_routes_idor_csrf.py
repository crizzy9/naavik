"""IDOR + CSRF coverage for `/api/v1/integrations/email/*` (plan 90 / 0.5.0.01).

Mirrors `tests/test_profile_settings_idor.py` — `require_authed_session`
overridden to User(id=42), then assertions verify the persisted EmailAccount
belongs to user 42 (NOT user 1). CSRF rejection proven by NOT overriding
the CSRF dep on a separate fixture.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles

os.environ.setdefault("NAAVIK_DEBUG", "1")
os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")


@pytest.fixture(autouse=True)
def _patch_imap_host_guard_dns(monkeypatch):
    """The connect route runs the SSRF host guard (real DNS). Map the canned
    test host to a public IP so the happy-path tests pass without live network;
    IP literals resolve to themselves."""
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


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw):  # type: ignore[misc]
    return "TEXT"


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_type, _compiler, **_kw):  # type: ignore[misc]
    return "TEXT"


def _email_test_tables():
    from sqlalchemy import CheckConstraint

    from models import (
        CalendarConnection,
        CompanyAlias,
        EmailAccount,
        EmailMessage,
        EmailThread,
        User,
    )

    tables = [
        User.__table__,
        EmailThread.__table__,
        EmailAccount.__table__,
        EmailMessage.__table__,
        CompanyAlias.__table__,
        # The Integrations page ctx reads the calendar connection (item 11).
        CalendarConnection.__table__,
    ]
    for table in tables:
        for c in list(table.constraints):
            if isinstance(c, CheckConstraint):
                table.constraints.discard(c)
        for idx in list(table.indexes):
            if any(getattr(o, "name", None) == "deleted_at" for o in idx.columns):
                table.indexes.discard(idx)
    return tables


@pytest.fixture
async def engine_with_seed():
    """In-memory engine with the email tables created + user 42 seeded."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool
    from sqlmodel.ext.asyncio.session import AsyncSession

    from models import User

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
        s.add(User(id=42, email="u42@x.test", password_hash="x", is_active=True))
        s.add(User(id=99, email="u99@x.test", password_hash="x", is_active=True))
        await s.commit()
    yield engine, maker
    await engine.dispose()


@pytest.fixture
def client_with_user_42(engine_with_seed):
    from fastapi.testclient import TestClient

    from api.auth import require_csrf
    from db.session import get_session
    from main import app
    from services.auth import require_authed_session

    _, maker = engine_with_seed

    user = SimpleNamespace(id=42, is_active=True, must_change_password=False, email="u42@x.test")

    async def _override_user():
        return user

    def _csrf_pass() -> None:
        return None

    async def _override_session():
        async with maker() as s:
            yield s

    app.dependency_overrides[require_authed_session] = _override_user
    app.dependency_overrides[require_csrf] = _csrf_pass
    app.dependency_overrides[get_session] = _override_session
    try:
        yield TestClient(app, raise_server_exceptions=True), user, maker
    finally:
        app.dependency_overrides.pop(require_authed_session, None)
        app.dependency_overrides.pop(require_csrf, None)
        app.dependency_overrides.pop(get_session, None)


@pytest.fixture
def client_with_user_42_no_csrf_override(engine_with_seed):
    """Same auth + session override, but `require_csrf` left intact so we can
    prove CSRF rejection on POST."""
    from fastapi.testclient import TestClient

    from db.session import get_session
    from main import app
    from services.auth import require_authed_session

    _, maker = engine_with_seed

    user = SimpleNamespace(id=42, is_active=True, must_change_password=False, email="u42@x.test")

    async def _override_user():
        return user

    async def _override_session():
        async with maker() as s:
            yield s

    app.dependency_overrides[require_authed_session] = _override_user
    app.dependency_overrides[get_session] = _override_session
    try:
        yield TestClient(app, raise_server_exceptions=False), user
    finally:
        app.dependency_overrides.pop(require_authed_session, None)
        app.dependency_overrides.pop(get_session, None)


async def test_post_imap_persists_user_id_from_auth(client_with_user_42):
    """Connect route persists EmailAccount with `user_id` from auth, never 1."""
    from sqlmodel import select

    from models import EmailAccount

    client, _, maker = client_with_user_42

    async def _spy_test_conn(*, host, port, username, password, client_factory=None):
        return True, None

    with patch("services.email.test_imap_connection", new=_spy_test_conn):
        r = client.post(
            "/api/v1/integrations/email/imap",
            data={
                "account_email": "u42@example.com",
                "imap_host": "imap.example.com",
                "imap_username": "u42@example.com",
                "imap_password": "secret-42",
            },
        )

    assert r.status_code == 200, r.text[:400]
    body = r.json()
    assert body["account_email"] == "u42@example.com"
    assert "imap_password" not in body
    assert "secret-42" not in r.text

    async with maker() as s:
        rows = (await s.exec(select(EmailAccount))).all()
    assert len(rows) == 1
    assert rows[0].user_id == 42, "IDOR regression: account user_id must come from auth, not 1"


async def test_post_imap_rejects_without_csrf_when_active(
    client_with_user_42_no_csrf_override,
):
    client, _ = client_with_user_42_no_csrf_override

    async def _spy_test_conn(*, host, port, username, password, client_factory=None):
        return True, None

    with patch("services.email.test_imap_connection", new=_spy_test_conn):
        r = client.post(
            "/api/v1/integrations/email/imap",
            data={
                "account_email": "u42@example.com",
                "imap_host": "imap.example.com",
                "imap_username": "u42@example.com",
                "imap_password": "secret-42",
            },
        )

    assert r.status_code == 403, r.text[:200]


async def test_delete_account_idor_404_on_cross_user(client_with_user_42):
    """User 42 may NOT delete an account owned by user 99."""
    from models import EmailAccount
    from models.enums import EmailAccountProvider

    client, _, maker = client_with_user_42

    async with maker() as s:
        account = EmailAccount(
            id=777,
            user_id=99,
            provider=EmailAccountProvider.IMAP,
            account_email="u99@x.test",
            imap_host="imap.example.com",
            imap_username="u99@x.test",
            imap_password="other-secret",
        )
        s.add(account)
        await s.commit()

    r = client.delete("/api/v1/integrations/email/777")
    assert r.status_code == 404


async def test_connect_blocks_internal_host_sanitized(client_with_user_42, monkeypatch):
    """Connect to an internal target is rejected 400 with a canonical message —
    no raw exception, no resolved-IP leak (PR #214 hacker H1)."""
    from services.email import imap_host_guard

    monkeypatch.setattr(imap_host_guard, "_resolve_host", lambda host: ("169.254.169.254",))

    client, _, _ = client_with_user_42
    r = client.post(
        "/api/v1/integrations/email/imap",
        data={
            "account_email": "u42@example.com",
            "imap_host": "metadata.internal",
            "imap_username": "u42@example.com",
            "imap_password": "secret-42",
        },
    )
    assert r.status_code == 400, r.text[:300]
    assert "169.254" not in r.text
    assert "not permitted" in r.text.lower()


async def test_connect_blocks_disallowed_port(client_with_user_42):
    """A non-IMAP port (e.g. loopback Ollama 11434) is rejected before DNS."""
    client, _, _ = client_with_user_42
    r = client.post(
        "/api/v1/integrations/email/imap",
        data={
            "account_email": "u42@example.com",
            "imap_host": "imap.example.com",
            "imap_username": "u42@example.com",
            "imap_password": "secret-42",
            "imap_port": "11434",
        },
    )
    assert r.status_code == 400, r.text[:300]
    assert "not permitted" in r.text.lower()


async def test_sync_now_rate_limited_1_per_min(client_with_user_42):
    """Second sync-now within a minute is 429 (plan 90 § H; architect MED)."""
    from models import EmailAccount
    from models.enums import EmailAccountProvider
    from services.email import sync as email_sync
    from services.utils import rate_limit

    client, _, maker = client_with_user_42
    rate_limit.reset_all()

    async with maker() as s:
        s.add(
            EmailAccount(
                id=501,
                user_id=42,
                provider=EmailAccountProvider.IMAP,
                account_email="u42@x.test",
                imap_host="imap.example.com",
                imap_username="u42@x.test",
                imap_password="",
            )
        )
        await s.commit()

    async def _spy_sync(session, account, *, client_factory=None):
        return email_sync.SyncResult(account_id=account.id or 0)

    with patch("services.email.sync_account", new=_spy_sync):
        r1 = client.post("/api/v1/integrations/email/501/sync-now")
        r2 = client.post("/api/v1/integrations/email/501/sync-now")

    assert r1.status_code == 200, r1.text[:300]
    assert r2.status_code == 429, r2.text[:300]
    rate_limit.reset_all()


# ── Items 3+4+8 (2026-07): visible feedback contracts ───────────────────


async def test_delete_account_returns_200_swap_plus_toast(client_with_user_42):
    """Disconnect must return 200 + empty body + a showToast HX-Trigger.

    Regression: the route returned 204 — htmx does NOT swap 204 responses,
    so the card stayed on screen and Disconnect looked dead even though the
    row was soft-deleted.
    """
    import json as _json

    from sqlmodel import select

    from models import EmailAccount
    from models.enums import EmailAccountProvider

    client, user, maker = client_with_user_42

    async with maker() as s:
        s.add(
            EmailAccount(
                id=555,
                user_id=user.id,
                provider=EmailAccountProvider.IMAP,
                account_email="mine@x.test",
                imap_host="imap.example.com",
                imap_username="mine@x.test",
                imap_password="",
            )
        )
        await s.commit()

    r = client.delete("/api/v1/integrations/email/555")
    assert r.status_code == 200, r.text[:200]
    assert r.text == ""
    trigger = _json.loads(r.headers["HX-Trigger"])
    assert trigger["showToast"]["tone"] == "success"
    assert "mine@x.test" in trigger["showToast"]["text"]

    async with maker() as s:
        row = (await s.exec(select(EmailAccount).where(EmailAccount.id == 555))).one()
    assert row.deleted_at is not None


async def test_connect_imap_htmx_failure_returns_visible_fragment(client_with_user_42):
    """HTMX callers get the connection error as an HTML fragment (lands in
    the hx-target-error slot) instead of a JSON 400 the page never shows."""
    client, _, _maker = client_with_user_42

    async def _fail_conn(*, host, port, username, password, client_factory=None):
        return False, "login rejected by server"

    with patch("services.email.test_imap_connection", new=_fail_conn):
        r = client.post(
            "/api/v1/integrations/email/imap",
            data={
                "account_email": "u42@example.com",
                "imap_host": "imap.example.com",
                "imap_username": "u42@example.com",
                "imap_password": "bad",
            },
            headers={"HX-Request": "true"},
        )
    assert r.status_code == 400
    assert "login rejected by server" in r.text
    assert r.text.strip().startswith("<div")


async def test_integrations_page_wires_error_targets(client_with_user_42):
    """The connect forms must declare hx-target-error so 4xx fragments are
    visible (422s used to be silently discarded by htmx)."""
    client, _, _maker = client_with_user_42
    r = client.get("/integrations/email")
    assert r.status_code == 200
    assert 'hx-target-error="#connect-gmail-result"' in r.text
    assert 'hx-target-error="#connect-imap-result"' in r.text
