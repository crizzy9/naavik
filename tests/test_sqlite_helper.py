"""Smoke test for the shared sqlite substrate (plan 91 Phase 0.2).

Proves `tests/_sqlite.py` imports and round-trips a row, so downstream
characterization + IDOR-sweep tests (Phases 1.1, 3.x) can rely on it.
"""

from __future__ import annotations

from tests._sqlite import USER_TABLES, sqlite_session


def test_user_tables_nonempty():
    assert len(USER_TABLES) >= 16


async def test_roundtrip_user():
    from models import User

    async with sqlite_session() as session:
        session.add(User(email="phase0@example.test", password_hash="x"))
        await session.commit()
        fetched = await session.get(User, 1)
    assert fetched is not None
    assert fetched.email == "phase0@example.test"


async def test_isolated_engines_do_not_share_rows():
    from models import User

    async with sqlite_session() as first:
        first.add(User(email="a@example.test", password_hash="x"))
        await first.commit()

    # A second session gets a fresh in-memory engine — no leakage.
    async with sqlite_session() as second:
        assert await second.get(User, 1) is None
