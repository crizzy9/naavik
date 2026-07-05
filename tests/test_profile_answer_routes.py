"""`/api/v1/profile-answers/{id}/accept` — plan 61 (0.2.7.14).

Smoke + IDOR coverage. Uses the existing FastAPI TestClient pattern;
session is mocked via dependency_overrides.
"""

from __future__ import annotations

import os

os.environ.setdefault("NAAVIK_DEBUG", "1")
os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")

from datetime import UTC, datetime  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
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


from main import app  # noqa: E402
from models import (  # noqa: E402
    Application,
    ApplicationScreenerAnswer,
    ProfileAnswer,
    User,
)
from models.enums import ApplicationStatus, ScreenerAnswerSource, ScreenerQuestionType  # noqa: E402
from services import profile_answer_service  # noqa: E402

pytestmark = pytest.mark.uses_sample_data_shims


def _strip_checks() -> list:
    from sqlalchemy import CheckConstraint

    tables = [
        User.__table__,
        Application.__table__,
        ApplicationScreenerAnswer.__table__,
        ProfileAnswer.__table__,
    ]
    for table in tables:
        for c in list(table.constraints):
            if isinstance(c, CheckConstraint):
                table.constraints.discard(c)
        for idx in list(table.indexes):
            if any(getattr(o, "name", None) == "deleted_at" for o in idx.columns):
                table.indexes.discard(idx)
    return tables


@pytest.fixture()
async def session_engine_factory():
    tables = _strip_checks()
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    async with engine.begin() as conn:
        for table in tables:
            await conn.run_sync(table.create)

    factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    yield engine, factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_accept_route_404_when_missing(session_engine_factory):
    """Cross-user / nonexistent ProfileAnswer.id → 404."""
    from db.session import get_session
    from services.auth import require_authed_session

    engine, factory = session_engine_factory

    async def _override_session():
        async with factory() as s:
            yield s
            await s.commit()

    def _stub_user():
        return User(id=99, email="other@x.com", password_hash="x")

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[require_authed_session] = _stub_user

    try:
        client = TestClient(app, headers={"X-CSRF-Token": "t"}, cookies={"naavik_csrf": "t"})
        r = client.post("/api/v1/profile-answers/12345/accept")
        assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_accept_route_happy_path(session_engine_factory):
    """Owner accepts → 200; ProfileAnswer.times_accepted increments."""
    from db.session import get_session
    from services.auth import require_authed_session

    engine, factory = session_engine_factory

    # Seed: user 1, application, screener answer, profile answer
    async with factory() as s:
        s.add(User(id=1, email="u1@x.com", password_hash="x"))
        await s.flush()
        app_row = Application(
            user_id=1,
            company="Acme",
            role="SWE",
            status=ApplicationStatus.DRAFT,
        )
        s.add(app_row)
        await s.flush()
        sa = ApplicationScreenerAnswer(
            application_id=app_row.id,
            question_text="Why us?",
            question_fingerprint="x",
            question_type=ScreenerQuestionType.TEXTAREA,
            answer="I want to.",
            source=ScreenerAnswerSource.DRAFTED,
            reviewed_at=datetime.now(UTC),
        )
        s.add(sa)
        await s.flush()
        pa = await profile_answer_service.upsert_from_screener_answer(
            s, user_id=1, screener_answer=sa, company_name="Acme"
        )
        await s.commit()
        target_id = pa.id

    async def _override_session():
        async with factory() as s:
            yield s

    def _stub_user():
        return User(id=1, email="u1@x.com", password_hash="x")

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[require_authed_session] = _stub_user

    try:
        client = TestClient(app, headers={"X-CSRF-Token": "t"}, cookies={"naavik_csrf": "t"})
        r = client.post(f"/api/v1/profile-answers/{target_id}/accept")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["profile_answer_id"] == target_id

        # Counter bumped in the database.
        async with factory() as s:
            from sqlmodel import select

            fresh = (
                await s.exec(select(ProfileAnswer).where(ProfileAnswer.id == target_id))
            ).one_or_none()
            assert fresh is not None
            assert fresh.times_accepted >= 1
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_accept_route_idor_404(session_engine_factory):
    """A different user trying to accept user 1's ProfileAnswer → 404."""
    from db.session import get_session
    from services.auth import require_authed_session

    engine, factory = session_engine_factory

    async with factory() as s:
        s.add(User(id=1, email="u1@x.com", password_hash="x"))
        s.add(User(id=2, email="u2@x.com", password_hash="x"))
        await s.flush()
        app_row = Application(user_id=1, company="Acme", role="SWE", status=ApplicationStatus.DRAFT)
        s.add(app_row)
        await s.flush()
        sa = ApplicationScreenerAnswer(
            application_id=app_row.id,
            question_text="Why us?",
            question_fingerprint="x",
            question_type=ScreenerQuestionType.TEXTAREA,
            answer="I want to.",
            source=ScreenerAnswerSource.DRAFTED,
            reviewed_at=datetime.now(UTC),
        )
        s.add(sa)
        await s.flush()
        pa = await profile_answer_service.upsert_from_screener_answer(
            s, user_id=1, screener_answer=sa, company_name="Acme"
        )
        await s.commit()
        target_id = pa.id

    async def _override_session():
        async with factory() as s:
            yield s

    def _stub_user_2():
        return User(id=2, email="u2@x.com", password_hash="x")

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[require_authed_session] = _stub_user_2

    try:
        client = TestClient(app, headers={"X-CSRF-Token": "t"}, cookies={"naavik_csrf": "t"})
        r = client.post(f"/api/v1/profile-answers/{target_id}/accept")
        assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()
