"""Screener-answer IDOR boundary — plan 75 / 0.3.3.15 (HIGH).

Multi-tenant readiness gate: `GET /_fragments/apply/screener/{app_id}/{q_id}`
+ `PUT /api/v1/applications/{app_id}/screeners/{q_id}` previously fetched by
bare `question_id` with no `Application.user_id` boundary. This file pins the
fix at the service layer (`owner_user_id` kwarg threads through a JOIN to
Application) and verifies the boundary holds for cross-user reads + writes.
"""

from __future__ import annotations

import os  # noqa: I001

os.environ.setdefault("NAAVIK_DEBUG", "1")
os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")

from datetime import UTC, datetime  # noqa: E402

import pytest  # noqa: E402
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


from models import (  # noqa: E402
    Application,
    ApplicationScreenerAnswer,
    User,
)
from models.enums import ApplicationStatus, ScreenerAnswerSource, ScreenerQuestionType  # noqa: E402
from services import application_service  # noqa: E402


def _strip_checks() -> list:
    from sqlalchemy import CheckConstraint

    tables = [
        User.__table__,
        Application.__table__,
        ApplicationScreenerAnswer.__table__,
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
async def session():
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
    async with factory() as s:
        yield s
    await engine.dispose()


async def _seed_users(session: AsyncSession) -> None:
    session.add_all(
        [
            User(id=1, email="u1@example.com", password_hash="x"),
            User(id=2, email="u2@example.com", password_hash="x"),
        ]
    )
    await session.flush()


async def _seed_application(session: AsyncSession, user_id: int) -> Application:
    app = Application(
        user_id=user_id,
        company="Acme",
        role="Senior SWE",
        status=ApplicationStatus.DRAFT,
    )
    session.add(app)
    await session.flush()
    return app


async def _seed_screener(
    session: AsyncSession, app_id: int, answer: str = "secret"
) -> ApplicationScreenerAnswer:
    row = ApplicationScreenerAnswer(
        application_id=app_id,
        question_text="Why work here?",
        question_fingerprint="legacy-noop",
        question_type=ScreenerQuestionType.TEXTAREA,
        answer=answer,
        source=ScreenerAnswerSource.DRAFTED,
        reviewed_at=datetime.now(UTC),
    )
    session.add(row)
    await session.flush()
    return row


@pytest.mark.asyncio
async def test_get_screener_answer_blocks_cross_user(session: AsyncSession):
    """User 2 reading user 1's screener answer returns None."""
    await _seed_users(session)
    app1 = await _seed_application(session, user_id=1)
    sa1 = await _seed_screener(session, app1.id)

    leaked = await application_service.get_screener_answer(session, sa1.id, owner_user_id=2)
    assert leaked is None


@pytest.mark.asyncio
async def test_get_screener_answer_owner_passes(session: AsyncSession):
    """Owner reading own screener answer succeeds."""
    await _seed_users(session)
    app1 = await _seed_application(session, user_id=1)
    sa1 = await _seed_screener(session, app1.id, answer="my answer")

    hit = await application_service.get_screener_answer(session, sa1.id, owner_user_id=1)
    assert hit is not None
    assert hit.answer == "my answer"


@pytest.mark.asyncio
async def test_get_screener_answer_no_owner_preserves_legacy_bypass(
    session: AsyncSession,
):
    """`owner_user_id=None` is the fake-session/legacy path — no IDOR check."""
    await _seed_users(session)
    app1 = await _seed_application(session, user_id=1)
    sa1 = await _seed_screener(session, app1.id, answer="bypass")

    hit = await application_service.get_screener_answer(session, sa1.id)
    assert hit is not None
    assert hit.answer == "bypass"


@pytest.mark.asyncio
async def test_record_screener_answer_blocks_cross_user_writes(session: AsyncSession):
    """User 2 writing to user 1's screener returns None — clean 404 in route."""
    await _seed_users(session)
    app1 = await _seed_application(session, user_id=1)
    sa1 = await _seed_screener(session, app1.id, answer="original")

    blocked = await application_service.record_screener_answer(
        session, sa1.id, "MALICIOUS", owner_user_id=2
    )
    assert blocked is None
    # Verify the row stayed unmodified.
    fresh = await application_service.get_screener_answer(session, sa1.id, owner_user_id=1)
    assert fresh is not None
    assert fresh.answer == "original"


@pytest.mark.asyncio
async def test_record_screener_answer_owner_succeeds(session: AsyncSession):
    """Owner writes go through and stamp reviewed_at."""
    await _seed_users(session)
    app1 = await _seed_application(session, user_id=1)
    sa1 = await _seed_screener(session, app1.id, answer="draft")

    updated = await application_service.record_screener_answer(
        session, sa1.id, "final answer", owner_user_id=1
    )
    assert updated is not None
    assert updated.answer == "final answer"
    assert updated.reviewed_at is not None
