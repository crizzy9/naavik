"""Regression tests for the production-hardening pass.

Covers the highest-severity fixes:
  1. Fake-session (`naavik_session=fake-1`) auth bypass is gated behind debug.
  2. Bullet mutation endpoints enforce ownership (IDOR → 404).
  3. `account_service.delete_user_account` really removes owned rows.
  4. Cover-letter section text persists per-application (not a global dict).
"""

from __future__ import annotations

import os

os.environ.setdefault("NAAVIK_DEBUG", "1")
os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")

from datetime import UTC, datetime  # noqa: E402

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from sqlalchemy.dialects.postgresql import ARRAY, JSONB  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel.ext.asyncio.session import AsyncSession  # noqa: E402


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw):  # type: ignore[misc]
    return "TEXT"


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_type, _compiler, **_kw):  # type: ignore[misc]
    return "TEXT"


from pgvector.sqlalchemy import Vector  # noqa: E402


@compiles(Vector, "sqlite")
def _compile_vector_sqlite(_type, _compiler, **_kw):  # type: ignore[misc]
    return "TEXT"


from models import (  # noqa: E402
    Application,
    Experience,
    GeneratedDocument,
    Profile,
    User,
)
from models.enums import ApplicationStatus, GeneratedDocumentKind  # noqa: E402

pytestmark = pytest.mark.uses_sample_data_shims


# ── 1. Fake-session auth bypass is gated behind debug ────────────────────


@pytest.mark.asyncio
async def test_fake_session_rejected_when_not_debug(monkeypatch):
    """`fake-1` must NOT authenticate outside dev (production hardening)."""
    from types import SimpleNamespace

    import config
    from services import auth as auth_mod

    request = SimpleNamespace(headers={}, url=SimpleNamespace(path="/"), method="GET")
    monkeypatch.setattr(config.settings, "debug", False)
    with pytest.raises(HTTPException) as exc:
        await auth_mod.require_authed_session(
            request=request, session=None, naavik_session="fake-1"
        )
    # 307 (browser redirect to /login) or 401 — both are "not authenticated".
    assert exc.value.status_code in (307, 401)


@pytest.mark.asyncio
async def test_fake_session_allowed_when_debug(monkeypatch):
    """`fake-1` still works in dev (NAAVIK_DEBUG=1) → returns None."""
    from types import SimpleNamespace

    import config
    from services import auth as auth_mod

    request = SimpleNamespace(headers={}, url=SimpleNamespace(path="/"), method="GET")
    monkeypatch.setattr(config.settings, "debug", True)
    result = await auth_mod.require_authed_session(
        request=request, session=None, naavik_session="fake-1"
    )
    assert result is None


# ── DB harness for ownership + deletion + cover-section tests ─────────────


def _tables():
    """All model tables (the delete service touches most of them), with
    Postgres-only CheckConstraints stripped so SQLite DDL compiles."""
    from sqlalchemy import CheckConstraint
    from sqlmodel import SQLModel

    import models  # noqa: F401 — registers metadata

    tables = list(SQLModel.metadata.tables.values())
    for table in tables:
        for c in list(table.constraints):
            if isinstance(c, CheckConstraint):
                table.constraints.discard(c)
        for idx in list(table.indexes):
            if any(getattr(o, "name", None) == "deleted_at" for o in idx.columns):
                table.indexes.discard(idx)
    return tables


@pytest.fixture()
async def factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    async with engine.begin() as conn:
        for table in _tables():
            await conn.run_sync(table.create)
    yield sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


async def _seed_user_with_bullet(s: AsyncSession, user_id: int) -> int:
    now = datetime.now(UTC)
    s.add(User(id=user_id, email=f"u{user_id}@x.test", password_hash="x"))
    await s.flush()
    prof = Profile(user_id=user_id, full_name="U", headline="", email=f"u{user_id}@x.test")
    s.add(prof)
    await s.flush()
    exp = Experience(profile_id=prof.id, company="C", title="T", start_date=now)
    s.add(exp)
    await s.flush()
    # Insert the Bullet via raw SQL: its `tags` column is a Postgres ARRAY that
    # the SQLite test backend can't bind from a Python list. `tags` is stored
    # as TEXT here (compiled above); ownership tests don't read it.
    from sqlalchemy import text as _text

    result = await s.execute(
        _text(
            "INSERT INTO bullet (experience_id, order_index, text, tags, created_at, updated_at) "
            "VALUES (:eid, 0, 'did a thing', '{}', :now, :now)"
        ),
        {"eid": exp.id, "now": now},
    )
    return int(result.lastrowid)


# ── 2. Bullet ownership guards ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_owns_bullet_true_for_owner_false_for_other(factory):
    from services import profile_service

    async with factory() as s:
        bullet_id = await _seed_user_with_bullet(s, user_id=1)
        await _seed_user_with_bullet(s, user_id=2)
        await s.commit()

        assert await profile_service.owns_bullet(s, bullet_id=bullet_id, user_id=1) is True
        assert await profile_service.owns_bullet(s, bullet_id=bullet_id, user_id=2) is False
        assert await profile_service.owns_bullet(s, bullet_id=999, user_id=1) is False


# ── 3. Account deletion removes owned rows ───────────────────────────────


@pytest.mark.asyncio
async def test_delete_user_account_removes_owned_rows(factory):
    from sqlmodel import func, select

    from services import account_service

    async with factory() as s:
        await _seed_user_with_bullet(s, user_id=1)
        keep_bullet = await _seed_user_with_bullet(s, user_id=2)
        await s.commit()

        deleted = await account_service.delete_user_account(s, user_id=1)
        await s.commit()
        assert deleted is True

        # User 1's data is gone; user 2's survives.
        assert (await s.exec(select(func.count(User.id)).where(User.id == 1))).one() == 0
        assert (await s.exec(select(func.count(Profile.id)).where(Profile.user_id == 1))).one() == 0
        assert (await s.exec(select(func.count(User.id)).where(User.id == 2))).one() == 1
        from services import profile_service

        assert await profile_service.owns_bullet(s, bullet_id=keep_bullet, user_id=2) is True

        # Deleting a nonexistent user is a no-op returning False.
        assert await account_service.delete_user_account(s, user_id=999) is False


# ── 4. Cover-letter section persistence (per application, IDOR-checked) ───


@pytest.mark.asyncio
async def test_cover_section_persists_and_is_owner_scoped(factory):
    from services import applications as application_service

    async with factory() as s:
        s.add(User(id=1, email="u1@x.test", password_hash="x"))
        s.add(User(id=2, email="u2@x.test", password_hash="x"))
        await s.flush()
        app = Application(user_id=1, company="Acme", role="Eng", status=ApplicationStatus.DRAFT)
        s.add(app)
        await s.flush()
        s.add(
            GeneratedDocument(
                application_id=app.id,
                kind=GeneratedDocumentKind.COVER_LETTER,
                path="/tmp/cl.pdf",
                byte_size=1,
                compiled_at=datetime.now(UTC),
                bullet_selection={"sections": {"intro": "hello"}},
            )
        )
        await s.commit()

        # Owner edit persists.
        ok = await application_service.update_cover_section(
            s, application_id=app.id, user_id=1, section="body", text="the body"
        )
        assert ok is True
        await s.commit()
        fetched = await application_service.get_latest_cover_sections(s, app.id)
        assert fetched["body"] == "the body"
        assert fetched["intro"] == "hello"

        # Cross-user edit is rejected (IDOR).
        assert (
            await application_service.update_cover_section(
                s, application_id=app.id, user_id=2, section="body", text="hacked"
            )
            is False
        )
