"""Enrichment merge on cross-source dedup — plan 95 § 3.10 (slice 95k).

A scraper re-find upgrades the tracked stub IN PLACE: identity (source,
external_id, queue_state, Application links) never moves; substance
(description, salary, URL) upgrades; score/embedding re-queue.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime

import pytest
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles

os.environ.setdefault("NAAVIK_DEBUG", "1")

sqlite3.register_adapter(list, json.dumps)
sqlite3.register_adapter(dict, json.dumps)


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


def _tables():
    from sqlalchemy import CheckConstraint

    from models import AppEvent, Application, Job, JobEmbedding, User

    tables = [
        User.__table__,
        Job.__table__,
        Application.__table__,
        AppEvent.__table__,
        JobEmbedding.__table__,
    ]
    for table in tables:
        for c in list(table.constraints):
            if isinstance(c, CheckConstraint):
                table.constraints.discard(c)
        for idx in list(table.indexes):
            if "gin" in (idx.name or "").lower():
                table.indexes.discard(idx)
    return tables


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


@pytest.fixture
async def user(session):
    from models import User

    u = User(email="merge@example.com", password_hash="x", is_active=True)
    session.add(u)
    await session.flush()
    return u


_STUB_DESCRIPTION = (
    "Tracked from the interview email “Interview with Camber” received "
    "2026-07-01. No posting URL was present — edit this job to attach one."
)


def _job(user_id: int, **overrides):
    from models import Job
    from models.enums import ApplicationBoard, JobSource

    external_id = overrides.get("external_id", f"e-{overrides.get('company', 'x')}")
    base = {
        "user_id": user_id,
        "source": JobSource.EMAIL,
        "board": ApplicationBoard.COMPANY_DIRECT,
        "external_id": external_id,
        "url": f"manual://email/{external_id}",
        "url_type": "email_receipt",
        "company": "Camber",
        "role": "Senior Software Engineer",
        "description": _STUB_DESCRIPTION,
        "found_at": datetime.now(UTC),
        "score": 0.42,
    }
    base.update(overrides)
    return Job(**base)


async def _seed_pair(session, user_id: int):
    from models.enums import ApplicationBoard, JobQueueState, JobSource

    canonical = _job(user_id, queue_state=JobQueueState.APPLIED)
    session.add(canonical)
    await session.flush()
    shadow = _job(
        user_id,
        source=JobSource.GREENHOUSE,
        board=ApplicationBoard.GREENHOUSE,
        external_id="gh-123",
        url="https://boards.greenhouse.io/camber/jobs/123",
        url_type="ats",
        description="Full JD: build health-data infrastructure at Camber…",
        salary_min=180000,
        salary_max=220000,
        location="Remote (US)",
        duplicate_of_id=canonical.id,
        score=0.0,
    )
    session.add(shadow)
    await session.flush()
    return canonical, shadow


async def test_stub_replaced_and_identity_untouched(session, user):
    from models.enums import JobQueueState, JobSource
    from services.jobs import dedup

    canonical, shadow = await _seed_pair(session, user.id)
    changed = await dedup.enrich_canonical(session, canonical=canonical, shadow=shadow)
    assert changed is True

    # Substance upgraded…
    assert canonical.url == "https://boards.greenhouse.io/camber/jobs/123"
    assert canonical.url_type == "ats"
    assert canonical.description.startswith("Full JD:")
    assert canonical.salary_min == 180000
    assert canonical.location == "Remote (US)"
    # …identity + human state untouched (§ 3.10 "never touched" row).
    assert canonical.source == JobSource.EMAIL
    assert canonical.external_id == "e-x"  # unchanged from seed
    assert canonical.queue_state == JobQueueState.APPLIED
    assert shadow.duplicate_of_id == canonical.id  # shadow stays shadowed
    # Score cleared → re-queued by the score-pending cron.
    assert canonical.score == 0.0


async def test_human_typed_description_never_replaced(session, user):
    from services.jobs import dedup

    canonical, shadow = await _seed_pair(session, user.id)
    canonical.description = "I met the team at a conference; comp flexible, series B."
    session.add(canonical)
    await session.flush()

    await dedup.enrich_canonical(session, canonical=canonical, shadow=shadow)
    assert canonical.description == "I met the team at a conference; comp flexible, series B."
    # Non-description substance still fills.
    assert canonical.salary_min == 180000


async def test_merge_is_idempotent(session, user):
    from services.jobs import dedup

    canonical, shadow = await _seed_pair(session, user.id)
    assert await dedup.enrich_canonical(session, canonical=canonical, shadow=shadow) is True
    marker = canonical.description
    # Re-running with the same shadow is a no-op — recorded in raw_meta.
    assert await dedup.enrich_canonical(session, canonical=canonical, shadow=shadow) is False
    assert canonical.description == marker
    assert canonical.raw_meta["enriched_from_shadow_ids"] == [shadow.id]


async def test_merge_emits_note_on_linked_application(session, user):
    from sqlmodel import select

    from models import AppEvent, Application
    from models.enums import AppEventKind, ApplicationStatus
    from services.jobs import dedup

    canonical, shadow = await _seed_pair(session, user.id)
    application = Application(
        user_id=user.id,
        job_id=canonical.id,
        company="Camber",
        role="Senior Software Engineer",
        status=ApplicationStatus.ONSITE_LOOP,
    )
    session.add(application)
    await session.flush()

    await dedup.enrich_canonical(session, canonical=canonical, shadow=shadow)
    events = (await session.exec(select(AppEvent))).all()
    notes = [e for e in events if e.kind == AppEventKind.NOTE_ADDED]
    assert len(notes) == 1
    assert notes[0].actor == "job_dedup_merge"
    assert notes[0].application_id == application.id


async def test_foreign_shadow_never_merges(session, user):
    """One-hop invariant: a row shadowing a DIFFERENT canonical is not a
    valid merge source."""
    from services.jobs import dedup

    canonical, shadow = await _seed_pair(session, user.id)
    other = _job(user.id, external_id="e-other", company="Other Co")
    session.add(other)
    await session.flush()
    shadow.duplicate_of_id = other.id
    session.add(shadow)
    await session.flush()

    assert await dedup.enrich_canonical(session, canonical=canonical, shadow=shadow) is False
    assert canonical.url.startswith("manual://email/")  # untouched


async def test_two_roles_same_company_never_dedup_match(session, user):
    """Characterization (§ 3.10 edge): 'Senior SWE' vs 'Staff PM' at one
    company stays two rows — role weight 0.4 + threshold 88 guards it."""
    from models.enums import JobSource
    from services.jobs import dedup

    swe = _job(user.id, external_id="e-swe", role="Senior Software Engineer")
    session.add(swe)
    await session.flush()

    match = await dedup.find_duplicate(
        session,
        user_id=user.id,
        company="Camber",
        role="Staff Product Manager",
        source=JobSource.GREENHOUSE,
    )
    assert match is None


async def test_upsert_job_wires_enrichment(session, user):
    """A scraper re-find through upsert_job upgrades the tracked stub in
    place — the § 6 acceptance, end to end."""
    from models.enums import JobQueueState
    from services import jobs as job_service
    from services.jobs import dedup as dedup_module

    canonical = _job(user.id, queue_state=JobQueueState.APPLIED)
    session.add(canonical)
    await session.flush()

    from models.enums import ApplicationBoard, JobSource

    job, created = await job_service.upsert_job(
        session,
        user_id=user.id,
        source=JobSource.GREENHOUSE,
        external_id="gh-999",
        raw={
            "board": ApplicationBoard.GREENHOUSE,
            "url": "https://boards.greenhouse.io/camber/jobs/999",
            "url_type": "ats",
            "company": "Camber",
            "role": "Senior Software Engineer",
            "description": "Full JD from the re-find…",
            "salary_min": 175000,
        },
    )
    assert created is True
    assert job.duplicate_of_id == canonical.id
    assert canonical.url == "https://boards.greenhouse.io/camber/jobs/999"
    assert canonical.description == "Full JD from the re-find…"
    assert canonical.queue_state == JobQueueState.APPLIED
    assert canonical.raw_meta[dedup_module._MERGE_SOURCES_KEY] == [job.id]
