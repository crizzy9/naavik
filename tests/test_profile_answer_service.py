"""profile_answer_service — plan 61 (0.2.7.14).

In-memory sqlite tests mirroring `tests/test_service_layer_parity.py`. Covers:
- Deterministic fingerprint algorithm
- Per-user `get_suggestion` (IDOR: no cross-user leak)
- `record_acceptance` bumps counters
- `upsert_from_screener_answer` last-write-wins
- `list_recent` ordering + scope
- `delete_answer` IDOR + happy path
"""

from __future__ import annotations

import os  # noqa: I001

os.environ.setdefault("NAAVIK_DEBUG", "1")
os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")

from datetime import UTC, datetime, timedelta  # noqa: E402

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


async def _seed_screener_answer(
    session: AsyncSession, app_id: int, *, question_text: str, answer: str
) -> ApplicationScreenerAnswer:
    row = ApplicationScreenerAnswer(
        application_id=app_id,
        question_text=question_text,
        question_fingerprint="legacy-noop",
        question_type=ScreenerQuestionType.TEXTAREA,
        answer=answer,
        source=ScreenerAnswerSource.DRAFTED,
        reviewed_at=datetime.now(UTC),
    )
    session.add(row)
    await session.flush()
    return row


# ── Fingerprint determinism ─────────────────────────────────────────────


def test_fingerprint_lowercase_punct_whitespace_invariant():
    fp_a = profile_answer_service.fingerprint("Why do you want to work here?")
    fp_b = profile_answer_service.fingerprint("WHY do YOU want to WORK here?")
    fp_c = profile_answer_service.fingerprint("  Why do  you   want to work  here? ")
    assert fp_a == fp_b == fp_c


def test_fingerprint_company_token_stripping():
    fp_acme = profile_answer_service.fingerprint(
        "Why do you want to work at Acme Inc?", company_name="Acme Inc"
    )
    fp_xyz = profile_answer_service.fingerprint(
        "Why do you want to work at XYZ Inc?", company_name="XYZ Inc"
    )
    assert fp_acme == fp_xyz


def test_fingerprint_stop_token_blocklist():
    """Curated blocklist tokens like `inc`, `corp` collapse."""
    fp_a = profile_answer_service.fingerprint("How would you scale our system?")
    fp_b = profile_answer_service.fingerprint("How would you scale system?")
    # `our` is in blocklist; result identical
    assert fp_a == fp_b


def test_fingerprint_differs_for_distinct_meaning():
    fp_a = profile_answer_service.fingerprint("Why do you want to work here?")
    fp_b = profile_answer_service.fingerprint("What is your salary expectation?")
    assert fp_a != fp_b


def test_fingerprint_is_sha1_hex_length():
    fp = profile_answer_service.fingerprint("a question")
    assert len(fp) == 40
    int(fp, 16)


# ── get_suggestion / per-user scoping ────────────────────────────────────


@pytest.mark.asyncio
async def test_get_suggestion_returns_match_for_same_user(session: AsyncSession):
    await _seed_users(session)
    app = await _seed_application(session, user_id=1)
    sa = await _seed_screener_answer(
        session, app.id, question_text="Why work here?", answer="I love mission"
    )
    await profile_answer_service.upsert_from_screener_answer(
        session, user_id=1, screener_answer=sa, company_name="Acme"
    )

    hit = await profile_answer_service.get_suggestion(
        session, user_id=1, question_text="Why work here?", company_name="Acme"
    )
    assert hit is not None
    assert hit.answer == "I love mission"
    assert hit.times_offered == 1


@pytest.mark.asyncio
async def test_get_suggestion_returns_none_cross_user(session: AsyncSession):
    """IDOR — user 2 must never see user 1's reuse cache."""
    await _seed_users(session)
    app1 = await _seed_application(session, user_id=1)
    sa1 = await _seed_screener_answer(
        session, app1.id, question_text="Why work here?", answer="user 1 answer"
    )
    await profile_answer_service.upsert_from_screener_answer(
        session, user_id=1, screener_answer=sa1, company_name="Acme"
    )

    hit_user2 = await profile_answer_service.get_suggestion(
        session, user_id=2, question_text="Why work here?", company_name="Acme"
    )
    assert hit_user2 is None


@pytest.mark.asyncio
async def test_get_suggestion_miss_returns_none(session: AsyncSession):
    await _seed_users(session)
    hit = await profile_answer_service.get_suggestion(
        session, user_id=1, question_text="unseen question"
    )
    assert hit is None


# ── upsert_from_screener_answer ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_upsert_creates_new_row(session: AsyncSession):
    await _seed_users(session)
    app = await _seed_application(session, user_id=1)
    sa = await _seed_screener_answer(
        session, app.id, question_text="What is your salary?", answer="$200k"
    )
    row = await profile_answer_service.upsert_from_screener_answer(
        session, user_id=1, screener_answer=sa
    )
    assert row is not None
    assert row.user_id == 1
    assert row.answer == "$200k"


@pytest.mark.asyncio
async def test_upsert_collision_last_write_wins(session: AsyncSession):
    await _seed_users(session)
    app = await _seed_application(session, user_id=1)
    sa1 = await _seed_screener_answer(session, app.id, question_text="Salary?", answer="$200k")
    sa2 = await _seed_screener_answer(session, app.id, question_text="Salary?", answer="$220k")
    row1 = await profile_answer_service.upsert_from_screener_answer(
        session, user_id=1, screener_answer=sa1
    )
    row2 = await profile_answer_service.upsert_from_screener_answer(
        session, user_id=1, screener_answer=sa2
    )
    assert row1.id == row2.id
    assert row2.answer == "$220k"


@pytest.mark.asyncio
async def test_upsert_empty_answer_is_noop(session: AsyncSession):
    await _seed_users(session)
    app = await _seed_application(session, user_id=1)
    sa = await _seed_screener_answer(session, app.id, question_text="q", answer="")
    row = await profile_answer_service.upsert_from_screener_answer(
        session, user_id=1, screener_answer=sa
    )
    assert row is None


# ── record_acceptance ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_record_acceptance_bumps_counters(session: AsyncSession):
    await _seed_users(session)
    app = await _seed_application(session, user_id=1)
    sa = await _seed_screener_answer(session, app.id, question_text="q", answer="a")
    row = await profile_answer_service.upsert_from_screener_answer(
        session, user_id=1, screener_answer=sa
    )
    before = row.times_accepted
    ok = await profile_answer_service.record_acceptance(
        session, user_id=1, profile_answer_id=row.id
    )
    assert ok is True
    assert row.times_accepted == before + 1


@pytest.mark.asyncio
async def test_record_acceptance_cross_user_idor(session: AsyncSession):
    """User 2 cannot accept user 1's ProfileAnswer."""
    await _seed_users(session)
    app = await _seed_application(session, user_id=1)
    sa = await _seed_screener_answer(session, app.id, question_text="q", answer="a")
    row = await profile_answer_service.upsert_from_screener_answer(
        session, user_id=1, screener_answer=sa
    )
    ok = await profile_answer_service.record_acceptance(
        session, user_id=2, profile_answer_id=row.id
    )
    assert ok is False


# ── list_recent + delete ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_recent_orders_and_scopes(session: AsyncSession):
    await _seed_users(session)
    app1 = await _seed_application(session, user_id=1)
    app2 = await _seed_application(session, user_id=2)
    sa1 = await _seed_screener_answer(session, app1.id, question_text="Q1?", answer="A1")
    sa2 = await _seed_screener_answer(session, app1.id, question_text="Q2?", answer="A2")
    sa_other = await _seed_screener_answer(
        session, app2.id, question_text="Other Q?", answer="other"
    )
    r1 = await profile_answer_service.upsert_from_screener_answer(
        session, user_id=1, screener_answer=sa1
    )
    r2 = await profile_answer_service.upsert_from_screener_answer(
        session, user_id=1, screener_answer=sa2
    )
    await profile_answer_service.upsert_from_screener_answer(
        session, user_id=2, screener_answer=sa_other
    )
    # Sleep-equivalent: tweak r1's last_used_at backward
    r1.last_used_at = datetime.now(UTC) - timedelta(hours=1)
    session.add(r1)
    await session.flush()

    listed = await profile_answer_service.list_recent(session, user_id=1, limit=10)
    listed_ids = [r.id for r in listed]
    assert r2.id in listed_ids
    assert r1.id in listed_ids
    # user 2's row excluded
    assert all(r.user_id == 1 for r in listed)
    # most recent first
    assert listed_ids.index(r2.id) < listed_ids.index(r1.id)


@pytest.mark.asyncio
async def test_delete_answer_happy_and_cross_user(session: AsyncSession):
    await _seed_users(session)
    app = await _seed_application(session, user_id=1)
    sa = await _seed_screener_answer(session, app.id, question_text="q", answer="a")
    row = await profile_answer_service.upsert_from_screener_answer(
        session, user_id=1, screener_answer=sa
    )
    # Cross-user delete must fail.
    ok = await profile_answer_service.delete_answer(session, user_id=2, profile_answer_id=row.id)
    assert ok is False
    # Owner delete succeeds.
    ok = await profile_answer_service.delete_answer(session, user_id=1, profile_answer_id=row.id)
    assert ok is True
