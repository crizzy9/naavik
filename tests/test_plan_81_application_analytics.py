"""Plan 81 § D.4 (0.4.0.07) — application analytics + dashboard tests.

Covers:

- `compute_kpis` empty history → 0.0 rates, no div-by-zero.
- `compute_kpis` basic — known applied → recruiter → onsite path; rates match.
- `compute_kpis` window filters out applications older than `window_days`.
- `compute_kpis` cross-user safety (IDOR — `user_id=42` query excludes user 1).
- `kpis_by_company` returns sorted-by-applied list.
- `GET /tracking/analytics` page renders 4-KPI strip + funnel + company table.
- Route order: `/tracking/analytics` (literal) MUST resolve before
  `/tracking/<application_id>` (dynamic).
"""

from __future__ import annotations

import os  # noqa: I001

os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")
os.environ.setdefault("NAAVIK_DEBUG", "1")

from datetime import UTC, datetime, timedelta  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy import CheckConstraint  # noqa: E402
from sqlalchemy.dialects.postgresql import ARRAY, JSONB  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402
from sqlmodel.ext.asyncio.session import AsyncSession  # noqa: E402


# Mirror `tests/test_service_layer_parity.py` — teach sqlite to render
# Postgres ARRAY / JSONB as TEXT for DDL compilation. We only use the
# Application + AppEvent tables in this module; no ARRAY columns are read.
@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw):  # type: ignore[misc]
    return "TEXT"


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_type, _compiler, **_kw):  # type: ignore[misc]
    return "TEXT"


from models import AppEvent, Application  # noqa: E402


def _strip_pg_checks() -> list:
    tables = [Application.__table__, AppEvent.__table__]
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


_USER_TABLES = _strip_pg_checks()


@pytest.fixture
async def session() -> AsyncSession:
    """In-memory sqlite session — Application + AppEvent tables only."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(lambda sc: SQLModel.metadata.create_all(sc, tables=_USER_TABLES))
    sm = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sm() as s:
        yield s
    await engine.dispose()


async def _make_app(
    session: AsyncSession,
    *,
    aid: int,
    user_id: int = 1,
    company: str = "Acme",
    status_value: str = "APPLIED",
    applied_days_ago: int = 5,
) -> int:
    from models import Application
    from models.enums import (
        ApplicationStatus,
        DocsState,
        RecruiterState,
        ReferralState,
    )

    now = datetime.now(UTC)
    applied = now - timedelta(days=applied_days_ago)
    a = Application(
        id=aid,
        user_id=user_id,
        job_id=None,
        company=company,
        role="Engineer",
        applied_at=applied,
        board=None,
        external_url=None,
        status=ApplicationStatus(status_value),
        docs_state=DocsState.NONE,
        referral_state=ReferralState.NONE,
        recruiter_state=RecruiterState.NONE,
        notes=None,
        created_at=applied,
        updated_at=applied,
    )
    session.add(a)
    await session.commit()
    return a.id


async def _emit_status_change(
    session: AsyncSession, *, aid: int, user_id: int = 1, to: str
) -> None:
    from models import AppEvent
    from models.enums import AppEventKind

    e = AppEvent(
        user_id=user_id,
        application_id=aid,
        kind=AppEventKind.STATUS_CHANGE,
        payload={"from": None, "to": to, "trigger": "manual"},
    )
    session.add(e)
    await session.commit()


# ── compute_kpis ──


@pytest.mark.asyncio
async def test_compute_kpis_empty_history(session: AsyncSession) -> None:
    """No applications → 0/0 → 0.0 rates, no div-by-zero."""
    from services import application_analytics as svc

    kpis = await svc.compute_kpis(session, user_id=1)
    assert kpis.applied_in_window == 0
    assert kpis.response_rate == 0.0
    assert kpis.onsite_rate == 0.0
    assert kpis.offer_rate == 0.0
    assert kpis.funnel.applied == 0
    assert kpis.funnel.offer == 0


@pytest.mark.asyncio
async def test_compute_kpis_basic_funnel(session: AsyncSession) -> None:
    """Known: 4 applied; 2 reach recruiter; 1 onsite; 1 offer."""
    from services import application_analytics as svc

    a1 = await _make_app(session, aid=1, company="A")
    a2 = await _make_app(session, aid=2, company="B")
    await _make_app(session, aid=3, company="C")
    await _make_app(session, aid=4, company="D")
    # a1: APPLIED → RECRUITER → ONSITE → OFFER
    await _emit_status_change(session, aid=a1, to="RECRUITER_SCREEN")
    await _emit_status_change(session, aid=a1, to="ONSITE_LOOP")
    await _emit_status_change(session, aid=a1, to="OFFER")
    # a2: APPLIED → RECRUITER only
    await _emit_status_change(session, aid=a2, to="RECRUITER_SCREEN")
    # a3 + a4: APPLIED only

    kpis = await svc.compute_kpis(session, user_id=1)
    assert kpis.applied_in_window == 4
    assert kpis.funnel.applied == 4
    assert kpis.funnel.recruiter == 2
    assert kpis.funnel.onsite == 1
    assert kpis.funnel.offer == 1
    assert kpis.response_rate == 0.5
    assert kpis.onsite_rate == 0.25
    assert kpis.offer_rate == 0.25


@pytest.mark.asyncio
async def test_compute_kpis_window_excludes_old_applications(session: AsyncSession) -> None:
    """Application applied 100 days ago is excluded from a 90-day window."""
    from services import application_analytics as svc

    await _make_app(session, aid=1, applied_days_ago=100)  # outside 90d
    await _make_app(session, aid=2, applied_days_ago=10)  # inside 90d

    kpis = await svc.compute_kpis(session, user_id=1, window_days=90)
    assert kpis.applied_in_window == 1
    assert kpis.funnel.applied == 1


@pytest.mark.asyncio
async def test_compute_kpis_cross_user_safety(session: AsyncSession) -> None:
    """Querying user_id=42 must NOT aggregate user_id=1's applications."""
    from services import application_analytics as svc

    a1 = await _make_app(session, aid=1, user_id=1)
    await _emit_status_change(session, aid=a1, to="OFFER")  # user 1 got an offer
    await _make_app(session, aid=2, user_id=42)  # user 42, just applied

    # Query as user 42 — must NOT see user 1's OFFER
    k42 = await svc.compute_kpis(session, user_id=42)
    assert k42.applied_in_window == 1
    assert k42.funnel.offer == 0
    assert k42.offer_rate == 0.0
    # Sanity — user 1 still sees their own data
    k1 = await svc.compute_kpis(session, user_id=1)
    assert k1.funnel.offer == 1


@pytest.mark.asyncio
async def test_compute_kpis_excludes_draft(session: AsyncSession) -> None:
    """DRAFT applications are not counted (no `applied_at`)."""
    # DRAFT: applied_at NULL — manually construct
    from models import Application
    from models.enums import (
        ApplicationStatus,
        DocsState,
        RecruiterState,
        ReferralState,
    )
    from services import application_analytics as svc

    now = datetime.now(UTC)
    a_draft = Application(
        id=1,
        user_id=1,
        job_id=None,
        company="Stuck",
        role="Engineer",
        applied_at=None,
        board=None,
        status=ApplicationStatus.DRAFT,
        docs_state=DocsState.NONE,
        referral_state=ReferralState.NONE,
        recruiter_state=RecruiterState.NONE,
        notes=None,
        created_at=now,
        updated_at=now,
    )
    session.add(a_draft)
    await session.commit()

    await _make_app(session, aid=2, status_value="APPLIED")

    kpis = await svc.compute_kpis(session, user_id=1)
    assert kpis.applied_in_window == 1  # only the APPLIED one


@pytest.mark.asyncio
async def test_kpis_by_company_returns_sorted(session: AsyncSession) -> None:
    from services import application_analytics as svc

    # Acme · 3 applications · 1 offer
    a1 = await _make_app(session, aid=1, company="Acme")
    await _make_app(session, aid=2, company="Acme")
    await _make_app(session, aid=3, company="Acme")
    await _emit_status_change(session, aid=a1, to="OFFER")
    # Beta · 1 application
    await _make_app(session, aid=4, company="Beta")

    rows = await svc.kpis_by_company(session, user_id=1)
    assert len(rows) == 2
    # Sorted by applied desc → Acme first
    assert rows[0].company == "Acme"
    assert rows[0].applied == 3
    assert rows[0].offer_rate == pytest.approx(1 / 3)
    assert rows[1].company == "Beta"
    assert rows[1].applied == 1
    assert rows[1].offer_rate == 0.0


# Analytics page route tests live in `tests/test_plan_81_analytics_page.py`
# (separate module so they can use the conftest `_patch_services_to_sample_data`
# fixture; this module is `_SERVICE_DIRECT_TEST_MODULES`-listed so the conftest
# autouse fixture is skipped and the real sqlite engine is used instead).
