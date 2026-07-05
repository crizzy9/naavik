"""`services.extraction._persist_profile` — structured parse persistence.

Pins the hardening-pass fixes:

1. ExtractedResume identity fields live at the TOP level of the payload —
   the old code read `structured["profile"]`, which never existed, so every
   parse persisted full_name="Unknown" and dropped the rest.
2. Educations / skills / projects are persisted (previously dropped).
3. Re-parsing REPLACES resume-derived sections instead of appending
   duplicates (owner directive: "Update Resume … replaces current content").
4. Bullet tags ride the parallel `bullet_tags` list.
5. `_parse_date` accepts full-ISO / YYYY-MM / YYYY and returns aware UTC.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession


# Teach the sqlite compiler to render JSONB / ARRAY as TEXT — DDL-compile
# unblock only (same shim as tests/test_service_layer_parity.py).
@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw):  # type: ignore[misc]
    return "TEXT"


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_type, _compiler, **_kw):  # type: ignore[misc]
    return "TEXT"


# sqlite3 can't bind Python lists (Postgres ARRAY params) — adapt to JSON
# text so `_persist_profile`'s ORM inserts work on the test backend.
import json as _json  # noqa: E402
import sqlite3 as _sqlite3  # noqa: E402

_sqlite3.register_adapter(list, _json.dumps)


import models  # noqa: F401,E402 — registers metadata
from models import (  # noqa: E402
    Bullet,
    Certification,
    Education,
    Experience,
    Profile,
    Project,
    Skill,
    User,
)
from services.profile.extraction import _parse_date, _persist_profile  # noqa: E402

_TABLES = [
    User.__table__,
    Profile.__table__,
    Experience.__table__,
    Bullet.__table__,
    Education.__table__,
    Skill.__table__,
    Project.__table__,
    Certification.__table__,
]


def _strip_pg_only() -> None:
    """Drop `char_length` CHECKs + GIN indexes sqlite can't evaluate."""
    from sqlalchemy import CheckConstraint

    for t in _TABLES:
        for c in [
            c
            for c in list(t.constraints)
            if isinstance(c, CheckConstraint) and "char_length" in str(c.sqltext)
        ]:
            t.constraints.discard(c)
        for i in [i for i in list(t.indexes) if "gin" in (i.name or "").lower()]:
            t.indexes.discard(i)


_strip_pg_only()

pytestmark = pytest.mark.uses_sample_data_shims

_PAYLOAD = {
    "full_name": "Ada Lovelace",
    "headline": "Analytical Engine Programmer",
    "email": "ada@example.com",
    "phone": "+1 555 0100",
    "location": "London",
    "summary_full": "First programmer.",
    "summary_short": "Programmer.",
    "experiences": [
        {
            "company": "Analytical Engines Ltd",
            "title": "Senior Engineer",
            "start_date": "2020-01",
            "end_date": "2023-06",
            "bullets": ["Built the engine", "Wrote the notes"],
            "bullet_tags": [["backend", "platform"], ["product"]],
        }
    ],
    "educations": [
        {
            "institution": "University of London",
            "degree": "MS Mathematics",
            "start_date": "1835",
            "end_date": "1837",
            "courses": ["Calculus"],
        }
    ],
    "skills": [{"category": "Languages", "items": ["Python", "Ada"]}],
    "projects": [
        {"title": "Bernoulli Numbers", "text": "First program", "tags": ["ai-ml"]},
        {
            "title": "Difference Engine",
            "text": "Contributed gear improvements",
            "kind": "open_source",
        },
    ],
    "certifications": [
        {
            "title": "Analytical Engine Operator",
            "issuer": "Royal Society",
            "date": "1842",
        }
    ],
}


@pytest.fixture
async def session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    def _create(sync_conn):
        SQLModel.metadata.create_all(sync_conn, tables=_TABLES)

    async with engine.begin() as conn:
        await conn.run_sync(_create)
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        s.add(
            User(
                id=1,
                email="ada@example.com",
                password_hash="x",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        await s.commit()
        yield s
    await engine.dispose()


@pytest.mark.asyncio
async def test_persist_reads_top_level_identity_fields(session):
    profile = await _persist_profile(session, user_id=1, structured=_PAYLOAD)
    assert profile.full_name == "Ada Lovelace"
    assert profile.headline == "Analytical Engine Programmer"
    assert profile.email == "ada@example.com"
    assert profile.summary_full == "First programmer."


@pytest.mark.asyncio
async def test_persist_writes_all_sections(session):
    from sqlalchemy import text

    await _persist_profile(session, user_id=1, structured=_PAYLOAD)
    experiences = (await session.exec(select(Experience))).all()
    assert len(experiences) == 1
    assert experiences[0].company == "Analytical Engines Ltd"

    # ARRAY columns are TEXT on the sqlite backend — read raw.
    bullet_rows = (
        await session.execute(text("SELECT text, tags FROM bullet ORDER BY order_index"))
    ).all()
    assert [r[0] for r in bullet_rows] == ["Built the engine", "Wrote the notes"]
    assert "backend" in bullet_rows[0][1] and "platform" in bullet_rows[0][1]
    assert "product" in bullet_rows[1][1]

    educations = (await session.exec(select(Education))).all()
    assert len(educations) == 1
    assert educations[0].institution == "University of London"

    skill_rows = (await session.execute(text("SELECT category, items FROM skill"))).all()
    assert len(skill_rows) == 1
    assert skill_rows[0][0] == "Languages"
    assert "Python" in skill_rows[0][1]

    projects_rows = (
        await session.execute(text("SELECT title, kind FROM project ORDER BY order_index"))
    ).all()
    assert [(r[0], r[1]) for r in projects_rows] == [
        ("Bernoulli Numbers", "project"),
        ("Difference Engine", "open_source"),
    ]

    certifications = (await session.exec(select(Certification))).all()
    assert len(certifications) == 1
    assert certifications[0].title == "Analytical Engine Operator"
    assert certifications[0].issuer == "Royal Society"
    # sqlite round-trips TIMESTAMPTZ as naive — compare the date parts only.
    assert certifications[0].date is not None
    assert certifications[0].date.replace(tzinfo=None) == datetime(1842, 1, 1)


@pytest.mark.asyncio
async def test_reparse_replaces_sections_not_appends(session):
    await _persist_profile(session, user_id=1, structured=_PAYLOAD)
    await _persist_profile(session, user_id=1, structured=_PAYLOAD)
    assert len((await session.exec(select(Experience))).all()) == 1
    assert len((await session.exec(select(Bullet))).all()) == 2
    assert len((await session.exec(select(Education))).all()) == 1
    assert len((await session.exec(select(Skill))).all()) == 1
    assert len((await session.exec(select(Project))).all()) == 2
    assert len((await session.exec(select(Certification))).all()) == 1


@pytest.mark.asyncio
async def test_persist_merge_keeps_hand_edits(session):
    await _persist_profile(session, user_id=1, structured=_PAYLOAD)
    profile = (await session.exec(select(Profile))).one()
    profile.full_name = "Hand Edited"
    session.add(profile)
    await session.flush()

    await _persist_profile(session, user_id=1, structured=_PAYLOAD)
    profile = (await session.exec(select(Profile))).one()
    assert profile.full_name == "Hand Edited"


def test_parse_date_variants():
    assert _parse_date("2023-06-15") == datetime(2023, 6, 15, tzinfo=UTC)
    assert _parse_date("2023-06") == datetime(2023, 6, 1, tzinfo=UTC)
    assert _parse_date("2023") == datetime(2023, 1, 1, tzinfo=UTC)
    assert _parse_date(None) is None
    assert _parse_date("Present") is None
    assert _parse_date("") is None
    parsed = _parse_date("2023-06-15T10:00:00Z")
    assert parsed is not None and parsed.tzinfo is not None
