"""Plan 91 Phase 3.3 — profile_service bullet CRUD + ownership on sqlite.

`add_bullet` / `update_bullet` / `delete_bullet` / `reorder_bullets` /
`owns_certification` were only exercised under the `NAAVIK_LIVE_DB` gate —
i.e. never in a normal run. These pins run them against the shared sqlite
substrate so the Phase-4 `profile_service` split has a net.

A scoped sqlite3 adapter serializes Python lists to JSON strings for the
duration of this module, so ORM writes of `Bullet.tags` (Postgres ARRAY)
bind on sqlite; nothing here reads the raw column back through ARRAY.
"""

from __future__ import annotations

import enum
import json
import sqlite3
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlmodel import select

from models import (
    Bullet,
    Certification,
    Education,
    Experience,
    Profile,
    Project,
    Settings,
    Skill,
    User,
)
from models.enums import BulletSelectionOverride
from services import profile as profile_service
from tests._sqlite import sqlite_session, strip_pg_checks

_NOW = datetime(2026, 7, 4, 12, 0, tzinfo=UTC)

_TABLES = strip_pg_checks(
    (User, Profile, Experience, Bullet, Education, Skill, Project, Certification, Settings)
)


@pytest.fixture(autouse=True)
def _sqlite_list_adapter():
    """Bind Python lists as JSON text on sqlite for this module only."""
    sqlite3.register_adapter(list, json.dumps)
    yield
    sqlite3.adapters.pop((list, sqlite3.PrepareProtocol), None)


async def _raw_insert(session, obj) -> int:
    table = type(obj).__table__
    params: dict[str, object] = {}
    for col in table.columns:
        if col.name == "id":
            continue
        v = getattr(obj, col.name, None)
        if isinstance(v, enum.Enum):
            v = v.name
        elif isinstance(v, (list, dict)):
            v = json.dumps(v)
        elif isinstance(v, datetime):
            v = v.isoformat(sep=" ")
        params[col.name] = v
    names = ", ".join(params)
    placeholders = ", ".join(f":{n}" for n in params)
    await session.execute(
        text(f"INSERT INTO {table.name} ({names}) VALUES ({placeholders})"), params
    )
    return int((await session.execute(text("SELECT last_insert_rowid()"))).scalar())


@pytest.fixture
async def world():
    """Two users, each with a profile + one experience; user 1 has a cert."""
    async with sqlite_session(tables=_TABLES) as s:
        s.add(User(id=1, email="owner@t.test", password_hash="x"))
        s.add(User(id=2, email="other@t.test", password_hash="x"))
        await s.flush()
        pids = {}
        for uid in (1, 2):
            pids[uid] = await _raw_insert(
                s,
                Profile(
                    user_id=uid,
                    full_name=f"U{uid}",
                    headline="Eng",
                    email=f"u{uid}@t.test",
                    created_at=_NOW,
                    updated_at=_NOW,
                ),
            )
        exps = {}
        for uid in (1, 2):
            exp = Experience(
                profile_id=pids[uid],
                company="Acme",
                title="Engineer",
                start_date=_NOW,
                created_at=_NOW,
                updated_at=_NOW,
            )
            s.add(exp)
            await s.flush()
            exps[uid] = exp
        cert = Certification(
            profile_id=pids[1],
            title="AWS SAA",
            issuer="AWS",
            created_at=_NOW,
            updated_at=_NOW,
        )
        s.add(cert)
        await s.flush()
        yield s, exps, cert


@pytest.mark.asyncio
async def test_add_bullet_appends_at_tail_with_defaults(world):
    session, exps, _ = world
    b = await profile_service.add_bullet(
        session, experience_id=exps[1].id, text="Did the thing.", tags=["ai-ml"]
    )
    assert b.id is not None
    assert b.order_index == 999  # tail sentinel; reorder normalizes
    assert b.edited_at is not None

    empty = await profile_service.add_bullet(session, experience_id=exps[1].id, text="")
    assert "edit to write" in empty.text  # placeholder, never an empty bullet


@pytest.mark.asyncio
async def test_update_bullet_sentinel_semantics(world):
    session, exps, _ = world
    b = await profile_service.add_bullet(session, experience_id=exps[1].id, text="Original.")
    before_edit = b.edited_at

    updated = await profile_service.update_bullet(
        session, b.id, text="Rewritten.", selection_override=BulletSelectionOverride.ALWAYS_INCLUDE
    )
    assert updated.text == "Rewritten."
    assert updated.selection_override == BulletSelectionOverride.ALWAYS_INCLUDE
    assert updated.edited_at >= before_edit

    # Omitting the kwarg leaves the override unchanged...
    updated = await profile_service.update_bullet(session, b.id, text="Rewritten again.")
    assert updated.selection_override == BulletSelectionOverride.ALWAYS_INCLUDE
    # ...while an explicit None clears back to "AI decides".
    updated = await profile_service.update_bullet(session, b.id, selection_override=None)
    assert updated.selection_override is None


@pytest.mark.asyncio
async def test_update_bullet_missing_raises_lookup_error(world):
    session, _, _ = world
    with pytest.raises(LookupError):
        await profile_service.update_bullet(session, 9999, text="x")


@pytest.mark.asyncio
async def test_delete_bullet_soft_deletes(world):
    session, exps, _ = world
    b = await profile_service.add_bullet(session, experience_id=exps[1].id, text="Gone soon.")
    assert await profile_service.delete_bullet(session, b.id) is True
    assert await profile_service.get_bullet(session, b.id) is None  # filtered read
    row = (await session.exec(select(Bullet).where(Bullet.id == b.id))).one()
    assert row.deleted_at is not None  # soft, not hard
    assert await profile_service.delete_bullet(session, b.id) is False  # already gone
    assert await profile_service.delete_bullet(session, 9999) is False


@pytest.mark.asyncio
async def test_reorder_bullets_applies_list_position(world):
    session, exps, _ = world
    ids = []
    for i in range(3):
        b = await profile_service.add_bullet(session, experience_id=exps[1].id, text=f"Bullet {i}.")
        ids.append(b.id)

    new_order = [ids[2], ids[0], ids[1]]
    result = await profile_service.reorder_bullets(
        session, experience_id=exps[1].id, bullet_ids=new_order
    )
    assert [b.id for b in result] == new_order
    assert [b.order_index for b in result] == [0, 1, 2]


@pytest.mark.asyncio
async def test_reorder_bullets_ignores_foreign_ids(world):
    session, exps, _ = world
    mine = await profile_service.add_bullet(session, experience_id=exps[1].id, text="Mine.")
    theirs = await profile_service.add_bullet(session, experience_id=exps[2].id, text="Theirs.")

    result = await profile_service.reorder_bullets(
        session, experience_id=exps[1].id, bullet_ids=[theirs.id, mine.id]
    )
    assert [b.id for b in result] == [mine.id]
    refreshed = await profile_service.get_bullet(session, theirs.id)
    assert refreshed.order_index == 999  # untouched


@pytest.mark.asyncio
async def test_owns_bullet_resolves_through_experience_profile_chain(world):
    session, exps, _ = world
    b = await profile_service.add_bullet(session, experience_id=exps[1].id, text="Owned.")
    assert await profile_service.owns_bullet(session, bullet_id=b.id, user_id=1) is True
    assert await profile_service.owns_bullet(session, bullet_id=b.id, user_id=2) is False
    await profile_service.delete_bullet(session, b.id)
    assert await profile_service.owns_bullet(session, bullet_id=b.id, user_id=1) is False


@pytest.mark.asyncio
async def test_owns_certification(world):
    session, _, cert = world
    assert (
        await profile_service.owns_certification(session, certification_id=cert.id, user_id=1)
        is True
    )
    assert (
        await profile_service.owns_certification(session, certification_id=cert.id, user_id=2)
        is False
    )
    assert (
        await profile_service.owns_certification(session, certification_id=9999, user_id=1) is False
    )
