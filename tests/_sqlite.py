"""Shared in-memory-sqlite test substrate (plan 91 Phase 0.2).

~22 service-layer test files hand-rolled the same block: teach the sqlite
compiler to render Postgres `JSONB`/`ARRAY` as `TEXT`, strip the Postgres-only
`char_length` CHECK constraints + GIN indexes off the shared SQLModel table
metadata, then `create_all` a subset of tables on a `StaticPool`
`sqlite+aiosqlite:///:memory:` engine. This module is the single source of
truth; the canonical origin is `tests/test_service_layer_parity.py:33-146`.

Usage in a test module::

    from tests._sqlite import sqlite_session

    @pytest.fixture
    async def session():
        async with sqlite_session() as s:
            yield s

Callers needing a different table set pass `tables=[Model.__table__, ...]`.
pgvector `Vector` columns are intentionally excluded from the default set (the
embedding tables need their own compiler shim); pass an explicit `tables` list
without them.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

if TYPE_CHECKING:
    from sqlalchemy import Table


# Render JSONB / ARRAY as TEXT so DDL compiles on sqlite; reads rely on
# SQLModel's plain JSON / list coercion. Registering twice for the same
# (type, dialect) key just overwrites — harmless alongside the legacy per-file
# copies during the migration to this helper.
@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw):  # type: ignore[misc]
    return "TEXT"


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_type, _compiler, **_kw):  # type: ignore[misc]
    return "TEXT"


from models import (  # noqa: E402  (import after compiler registration)
    AppEvent,
    Application,
    ApplicationScreenerAnswer,
    Bullet,
    Certification,
    Contact,
    ContactApplicationLink,
    Education,
    EmailThread,
    Experience,
    GeneratedDocument,
    OutreachMessage,
    Profile,
    Project,
    Skill,
    User,
)

# The proven default set (matches test_service_layer_parity.py). Excludes
# pgvector / Postgres-enum-heavy tables that need extra shimming.
_DEFAULT_MODELS = (
    User,
    Profile,
    Experience,
    Bullet,
    Skill,
    Education,
    Project,
    Certification,
    Application,
    GeneratedDocument,
    ApplicationScreenerAnswer,
    Contact,
    ContactApplicationLink,
    OutreachMessage,
    EmailThread,
    AppEvent,
)


def strip_pg_checks(models=_DEFAULT_MODELS) -> list[Table]:
    """Return the models' `Table` objects with Postgres-only `char_length`
    CHECK constraints and GIN indexes removed (idempotent — mutates the shared
    metadata in place, same as the legacy per-file blocks)."""
    tables: list[Table] = [m.__table__ for m in models]
    for t in tables:
        bad = [
            c
            for c in list(t.constraints)
            if isinstance(c, CheckConstraint) and "char_length" in str(c.sqltext)
        ]
        for c in bad:
            t.constraints.discard(c)
        bad_idx = [i for i in list(t.indexes) if "gin" in (i.name or "").lower()]
        for i in bad_idx:
            t.indexes.discard(i)
    return tables


USER_TABLES: list[Table] = strip_pg_checks()


async def make_engine(tables: list[Table] | None = None):
    """Build an in-memory sqlite engine with `tables` created (default:
    `USER_TABLES`). Caller owns disposal — prefer `sqlite_session`."""
    tables = USER_TABLES if tables is None else tables
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(lambda sc: SQLModel.metadata.create_all(sc, tables=tables))
    return engine


@asynccontextmanager
async def sqlite_session(tables: list[Table] | None = None):
    """Async context manager yielding an `AsyncSession` bound to a fresh
    in-memory sqlite engine; disposes the engine on exit."""
    engine = await make_engine(tables)
    session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with session_maker() as session:
            yield session
    finally:
        await engine.dispose()
