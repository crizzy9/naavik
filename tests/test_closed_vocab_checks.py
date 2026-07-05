"""Plan 94 slice C (plan 91 § 7.3) — closed-vocabulary CHECK constraints.

The 8 de-facto enum string columns carry DB-level CHECKs (model metadata →
sqlite test substrate; migration 0040 → Postgres). A writer drifting from
the vocabulary now fails loudly at INSERT instead of rendering as a blank
chip or silently skipping filters.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import CheckConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql.array import ARRAY as _PGARRAY
from sqlalchemy.ext.compiler import compiles


# sqlite DDL shims for the negative-INSERT test below — same pattern as
# tests/test_llm_tracker_judge_skipped.py (JSONB/ARRAY render as TEXT; lists
# JSON-encode on bind).
@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw):  # type: ignore[misc]
    return "TEXT"


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_type, _compiler, **_kw):  # type: ignore[misc]
    return "TEXT"


def _list_bind_processor(self, dialect):  # type: ignore[no-untyped-def]
    if dialect.name != "sqlite":
        return None

    def _process(value):
        if value is None:
            return None
        return json.dumps(list(value))

    return _process


_PGARRAY.bind_processor = _list_bind_processor

_EXPECTED = {
    "job": {
        "ck_job_url_type_vocab",
        "ck_job_apply_kind_vocab",
        "ck_job_apply_resolved_via_vocab",
    },
    "project": {"ck_project_kind_vocab"},
    "email_thread": {"ck_email_thread_provider_vocab"},
    "email_message": {"ck_email_message_provider_vocab"},
    "outreach_message": {"ck_outreach_message_channel_vocab"},
    "api_usage": {"ck_api_usage_method_vocab"},
}


@pytest.mark.parametrize(("table", "expected"), sorted(_EXPECTED.items()))
def test_vocab_checks_present_in_metadata(table: str, expected: set[str]):
    from sqlmodel import SQLModel

    import models  # noqa: F401 — register all tables

    tbl = SQLModel.metadata.tables[table]
    names = {c.name for c in tbl.constraints if isinstance(c, CheckConstraint) and c.name}
    missing = expected - names
    assert not missing, (
        f"{table} lost vocab CHECK(s) {sorted(missing)} — if a vocabulary "
        "legitimately grew, update the model constraint + a follow-up "
        "migration + this test in the same commit (plan 94 slice C)."
    )


@pytest.mark.asyncio
async def test_sqlite_substrate_rejects_out_of_vocab_url_type(tmp_path):
    """The model-level constraint applies on the sqlite test substrate too —
    a fixture writing a drifted vocabulary value fails at INSERT. Table
    setup mirrors the suite's Job-on-sqlite pattern (strip the Postgres-only
    char_length CHECKs + GIN indexes, keep everything else)."""
    from datetime import UTC, datetime

    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlmodel import SQLModel
    from sqlmodel.ext.asyncio.session import AsyncSession

    from models import Job, User

    tables = [User.__table__, Job.__table__]
    for tbl in tables:
        for c in [
            c
            for c in list(tbl.constraints)
            if isinstance(c, CheckConstraint) and "char_length" in str(c.sqltext)
        ]:
            tbl.constraints.discard(c)
        for i in [i for i in list(tbl.indexes) if "gin" in (i.name or "").lower()]:
            tbl.indexes.discard(i)

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/vocab.db")
    async with engine.begin() as conn:
        await conn.run_sync(lambda sc: SQLModel.metadata.create_all(sc, tables=tables))
    now = datetime.now(UTC)
    async with AsyncSession(engine) as session:
        session.add(
            Job(
                user_id=1,
                source="manual",
                board="manual",
                external_id="manual-x",
                url="https://example.com/job",
                url_type="bogus-vocab-drift",
                company="Acme",
                role="SWE",
                description="x",
                score=0.5,
                created_at=now,
                updated_at=now,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
    await engine.dispose()
