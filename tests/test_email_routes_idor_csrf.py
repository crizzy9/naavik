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


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw):  # type: ignore[misc]
    return "TEXT"


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_type, _compiler, **_kw):  # type: ignore[misc]
    return "TEXT"


def _email_test_tables():
    from sqlalchemy import CheckConstraint

    from models import (
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

    with patch("services.email_sync.test_imap_connection", new=_spy_test_conn):
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

    with patch("services.email_sync.test_imap_connection", new=_spy_test_conn):
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
