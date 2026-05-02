"""Idempotent seeding from `db/sample_data.py` into Postgres.

Per plan 10 § B.9 + SAMPLE_DATA.md § A. Reads every fixture list from the
Pydantic shadow models in `db/sample_data.py`, converts each row to its
SQLModel counterpart via `model_dump()`, and INSERTs in dependency order
with `ON CONFLICT (id) DO NOTHING` so reruns are safe.

CLI: `uv run python -m db.seed`. Called automatically by `nix run .#dev`
after `alembic upgrade head` succeeds (per plan 10 § B.9).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from db import sample_data as sd
from db.session import async_session, engine
from models import (
    ApiUsage,
    AppEvent,
    Application,
    ApplicationScreenerAnswer,
    ATSCredential,
    Bullet,
    Certification,
    Contact,
    ContactApplicationLink,
    Education,
    EmailThread,
    Experience,
    GeneratedDocument,
    Job,
    OutreachMessage,
    Profile,
    Project,
    Settings,
    Skill,
    User,
)

log = logging.getLogger(__name__)


# Insert order respects FK dependencies: parents → children. Each tuple is
# (sql_model_class, source_iterable, primary_key_columns_for_conflict).
_TABLE_ORDER: list[tuple[type[SQLModel], Sequence, tuple[str, ...]]] = [
    (User, [sd.USER], ("id",)),
    (Settings, [sd.SETTINGS], ("user_id",)),
    (Profile, [sd.PROFILE], ("id",)),
    (Experience, sd.EXPERIENCES, ("id",)),
    (Bullet, sd.BULLETS, ("id",)),
    (Skill, sd.SKILLS, ("id",)),
    (Education, sd.EDUCATIONS, ("id",)),
    (Project, sd.PROJECTS, ("id",)),
    (Certification, sd.CERTIFICATIONS, ("id",)),
    (Contact, sd.CONTACTS, ("id",)),
    (Job, sd.JOBS, ("id",)),
    (Application, sd.APPLICATIONS, ("id",)),
    (ContactApplicationLink, sd.CONTACT_APPLICATION_LINKS, ("id",)),
    (OutreachMessage, sd.OUTREACH_MESSAGES, ("id",)),
    (EmailThread, sd.EMAIL_THREADS, ("id",)),
    (AppEvent, sd.APP_EVENTS, ("id",)),
    (GeneratedDocument, sd.GENERATED_DOCUMENTS, ("id",)),
    (ApplicationScreenerAnswer, sd.SCREENER_ANSWERS, ("id",)),
    (ATSCredential, sd.ATS_CREDENTIALS, ("id",)),
    (ApiUsage, sd.API_USAGE, ("id",)),
]


def _shadow_to_payload(shadow_obj) -> dict:
    """Convert a Pydantic-shadow instance to a dict suitable for INSERT.

    Uses `model_dump(mode="python")` so `datetime` stays as `datetime`,
    enums stay as enum members, and SQLAlchemy + asyncpg get the native
    types they expect.
    """
    return shadow_obj.model_dump(mode="python")


async def _seed_one(
    session: AsyncSession,
    sql_cls: type[SQLModel],
    rows: Sequence,
    pk_cols: tuple[str, ...],
) -> int:
    """INSERT one table's rows with ON CONFLICT DO NOTHING.

    Returns the count of rows inserted (rowcount may be -1 with some drivers
    when ON CONFLICT skips; we count what we tried to insert).
    """
    if not rows:
        return 0
    payloads = [_shadow_to_payload(r) for r in rows]
    table = sql_cls.__table__
    stmt = pg_insert(table).values(payloads).on_conflict_do_nothing(index_elements=pk_cols)
    await session.exec(stmt)
    return len(payloads)


async def _bump_sequence(session: AsyncSession, table: str, pk_col: str = "id") -> None:
    """Bump the autoincrement sequence past the max id in the table.

    Required after `INSERT ... ON CONFLICT DO NOTHING` with explicit ids,
    since Postgres doesn't advance the sequence when the explicit PK is
    used. Without this, subsequent INSERTs that rely on the sequence
    (e.g. test fixtures appending new rows) collide with seeded ids.
    """
    from sqlalchemy import text

    # Default sequence name follows Postgres' implicit naming for SERIAL/IDENTITY.
    seq_name = f"{table}_{pk_col}_seq"
    sql = text(
        f"""
        SELECT setval(
            '{seq_name}',
            COALESCE((SELECT MAX({pk_col}) FROM "{table}"), 0) + 1,
            false
        )
        """
    )
    try:
        await session.exec(sql)
    except Exception as exc:  # noqa: BLE001
        log.warning("could not bump sequence %s: %s", seq_name, exc)


async def seed() -> dict[str, int]:
    """Idempotent seed across every fixture list. Returns inserted-count summary."""
    summary: dict[str, int] = {}
    async with async_session() as session:
        for sql_cls, rows, pk_cols in _TABLE_ORDER:
            count = await _seed_one(session, sql_cls, rows, pk_cols)
            summary[sql_cls.__name__] = count
            log.info("seed: %s × %d rows", sql_cls.__name__, count)
        # Advance every sequence past the seeded max so subsequent inserts
        # using SERIAL autoincrement don't collide with existing rows.
        for sql_cls, _, pk_cols in _TABLE_ORDER:
            if pk_cols == ("id",):
                await _bump_sequence(session, sql_cls.__tablename__, "id")
        await session.commit()
    return summary


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    summary = await seed()
    total = sum(summary.values())
    print(f"[seed] inserted {total} rows across {len(summary)} entities")
    for name, count in summary.items():
        print(f"  {name:32s} {count:5d}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
