"""Profile dossier CRUD — item 1 (2026-07).

The profile editor is fully self-serve: add/remove experience, education,
project (incl. open-source contributions via `Project.kind`), skills
groups, and certifications — plus per-field edits routed through the bulk
PUT's `<prefix>_<field>_<id>` parsing.

Service-layer tests use in-memory sqlite (same pattern as
`tests/test_service_layer_parity.py`); the bulk-PUT field parsing is pure
and unit-tested directly.
"""

from __future__ import annotations

import os  # noqa: I001

os.environ.setdefault("NAAVIK_DEBUG", "1")
os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")

import json  # noqa: E402
import sqlite3  # noqa: E402
from datetime import UTC, datetime  # noqa: E402

import pytest  # noqa: E402

# Postgres ARRAY columns compile to TEXT on sqlite (DDL below) but the ARRAY
# type has no sqlite bind processor — binding a Python list raises
# `type 'list' is not supported`. Adapt at the driver level.
sqlite3.register_adapter(list, json.dumps)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402
from sqlmodel.ext.asyncio.session import AsyncSession  # noqa: E402


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw):  # type: ignore[misc]
    return "TEXT"


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_type, _compiler, **_kw):  # type: ignore[misc]
    return "TEXT"


from models import (  # noqa: E402
    AppEvent,
    Bullet,
    Certification,
    Education,
    Experience,
    Profile,
    Project,
    Skill,
    User,
)
from services import profile_service  # noqa: E402


def _strip_pg_checks() -> list:
    from sqlalchemy import CheckConstraint

    tables = [
        User.__table__,
        Profile.__table__,
        Experience.__table__,
        Bullet.__table__,
        Skill.__table__,
        Education.__table__,
        Project.__table__,
        Certification.__table__,
        AppEvent.__table__,
    ]
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


_TABLES = _strip_pg_checks()


@pytest.fixture
async def session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(lambda sc: SQLModel.metadata.create_all(sc, tables=_TABLES))
    sm = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sm() as s:
        yield s
    await engine.dispose()


async def _seed(session: AsyncSession, user_id: int = 1) -> Profile:
    session.add(
        User(
            id=user_id,
            email=f"u{user_id}@local",
            password_hash="$2b$04$placeholder",
            is_active=True,
            must_change_password=False,
        )
    )
    p = Profile(
        user_id=user_id,
        full_name="Test User",
        headline="Engineer",
        email=f"u{user_id}@example.com",
    )
    session.add(p)
    await session.flush()
    return p


# ── Experience ──────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_add_update_delete_experience(session: AsyncSession):
    await _seed(session)
    exp = await profile_service.add_experience(session, 1)
    assert exp.id is not None
    assert await profile_service.owns_experience(session, experience_id=exp.id, user_id=1)

    updated = await profile_service.update_experience(
        session,
        exp.id,
        company="Acme",
        title="Staff Engineer",
        team="Platform",
        location="Remote",
        start_date=datetime(2023, 1, 1, tzinfo=UTC),
        end_date=datetime(2024, 6, 1, tzinfo=UTC),
    )
    assert updated.company == "Acme"
    assert updated.team == "Platform"

    assert await profile_service.delete_experience(session, exp.id)
    # Soft-deleted → ownership probe no longer matches.
    assert not await profile_service.owns_experience(session, experience_id=exp.id, user_id=1)


@pytest.mark.anyio
async def test_update_experience_rejects_inverted_dates(session: AsyncSession):
    await _seed(session)
    exp = await profile_service.add_experience(session, 1)
    with pytest.raises(ValueError, match="end date"):
        await profile_service.update_experience(
            session,
            exp.id,
            start_date=datetime(2024, 1, 1, tzinfo=UTC),
            end_date=datetime(2023, 1, 1, tzinfo=UTC),
        )


@pytest.mark.anyio
async def test_experience_ownership_is_per_user(session: AsyncSession):
    await _seed(session, user_id=1)
    await _seed(session, user_id=2)
    exp = await profile_service.add_experience(session, 1)
    assert not await profile_service.owns_experience(session, experience_id=exp.id, user_id=2)


# ── Education / Skill / Certification ───────────────────────────────────


@pytest.mark.anyio
async def test_education_crud(session: AsyncSession):
    await _seed(session)
    edu = await profile_service.add_education(session, 1)
    await profile_service.update_education(
        session,
        edu.id,
        institution="Northeastern University",
        degree="MS Computer Science",
        gpa="3.8/4.0",
        start_date=datetime(2017, 9, 1, tzinfo=UTC),
        end_date=datetime(2019, 12, 1, tzinfo=UTC),
    )
    rows = await profile_service.list_educations(session, 1)
    assert any(e.institution == "Northeastern University" for e in rows)
    assert await profile_service.delete_education(session, edu.id)
    assert not await profile_service.owns_education(session, education_id=edu.id, user_id=1)


@pytest.mark.anyio
async def test_skill_crud_normalizes_items(session: AsyncSession):
    await _seed(session)
    skill = await profile_service.add_skill(session, 1)
    updated = await profile_service.update_skill(
        session, skill.id, category="Languages", items=["Python", "  Go  ", ""]
    )
    assert updated.items == ["Python", "Go"]
    assert await profile_service.delete_skill(session, skill.id)


@pytest.mark.anyio
async def test_certification_crud(session: AsyncSession):
    await _seed(session)
    cert = await profile_service.add_certification(session, 1)
    await profile_service.update_certification(
        session,
        cert.id,
        title="AWS Solutions Architect",
        issuer="Amazon Web Services",
        date=datetime(2025, 11, 1, tzinfo=UTC),
    )
    rows = await profile_service.list_certifications(session, 1)
    assert rows and rows[0].title == "AWS Solutions Architect"
    assert await profile_service.delete_certification(session, cert.id)


# ── Projects + open-source kind ─────────────────────────────────────────


@pytest.mark.anyio
async def test_project_kind_split(session: AsyncSession):
    await _seed(session)
    proj = await profile_service.add_project(session, 1, kind="project")
    oss = await profile_service.add_project(session, 1, kind="open_source")
    assert proj.kind == "project"
    assert oss.kind == "open_source"
    with pytest.raises(ValueError):
        await profile_service.add_project(session, 1, kind="bogus")

    await profile_service.update_project(
        session, oss.id, title="cpython — asyncio patches", link="github.com/python/cpython"
    )
    rows = await profile_service.list_projects(session, 1)
    assert {p.kind for p in rows} == {"project", "open_source"}

    assert await profile_service.delete_project(session, oss.id)
    rows = await profile_service.list_projects(session, 1)
    assert all(p.kind == "project" for p in rows)


# ── Snapshot + resume payload carry the full dossier ────────────────────


@pytest.mark.anyio
async def test_snapshot_includes_certifications_and_open_source(session: AsyncSession):
    from services import document_generator as dg

    await _seed(session)
    await profile_service.add_certification(session, 1)
    await profile_service.add_project(session, 1, kind="open_source")
    await profile_service.add_project(session, 1, kind="project")

    snap = await dg.load_profile_snapshot(session, 1)
    assert snap is not None
    assert len(snap.certifications) == 1
    assert len(snap.open_source) == 1
    assert len(snap.projects) == 1

    data = await dg._build_resume_data(snap=snap, selected_bullet_ids=[], trimmed={})
    assert len(data["certifications"]) == 1
    assert len(data["open_source"]) == 1
    assert len(data["projects"]) == 1


@pytest.mark.anyio
async def test_resume_summary_falls_back_to_summary_full(session: AsyncSession):
    """`summary_full` is the user-editable master; without a tailored summary
    or `summary_short` it must still reach the resume payload."""
    from services import document_generator as dg

    profile = await _seed(session)
    profile.summary_full = "Full editable summary."
    profile.summary_short = None
    await session.flush()

    snap = await dg.load_profile_snapshot(session, 1)
    data = await dg._build_resume_data(snap=snap, selected_bullet_ids=[], trimmed={})
    assert data["summary"] == "Full editable summary."


# ── Bulk-PUT entity-field parsing (pure) ────────────────────────────────


def test_collect_entity_edits_groups_by_entity():
    from api.profile import _collect_entity_edits

    edits = _collect_entity_edits(
        [
            ("exp_company_12", "Acme"),
            ("exp_title_12", "Staff Engineer"),
            ("exp_start_12", "2023-01-01"),
            ("exp_end_12", ""),
            ("edu_gpa_3", "3.8"),
            ("cert_title_7", "AWS SA"),
            ("skill_items_4", "Python, Go , "),
            ("oss_title_9", "cpython"),
            ("full_name", "ignored — not an entity field"),
        ]
    )
    assert edits[("exp", 12)]["company"] == "Acme"
    assert edits[("exp", 12)]["start"] == datetime(2023, 1, 1, tzinfo=UTC)
    assert edits[("exp", 12)]["end"] is None
    assert edits[("edu", 3)]["gpa"] == "3.8"
    assert edits[("cert", 7)]["title"] == "AWS SA"
    assert edits[("skill", 4)]["items"] == ["Python", "Go"]
    assert edits[("oss", 9)]["title"] == "cpython"
    assert ("full_name", 0) not in edits


def test_collect_entity_edits_rejects_bad_date():
    from api.profile import _collect_entity_edits

    with pytest.raises(ValueError, match="bad date"):
        _collect_entity_edits([("exp_start_1", "not-a-date")])
