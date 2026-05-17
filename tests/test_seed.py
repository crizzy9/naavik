"""Live-DB seed tests — Wave 4 of plan 10 § B.9.

These tests are opt-in via `NAAVIK_LIVE_DB=1` env (with `DATABASE_URL`
pointing at a running Postgres). They use function-scoped fresh engines
to avoid pytest-asyncio's "Event loop is closed" cross-test issue.

Coverage:
- migration runs cleanly (verified separately via `alembic upgrade head`)
- `db.seed.seed()` populates every fixture; counts match SAMPLE_DATA.md
- re-running `seed()` is a no-op (ON CONFLICT DO NOTHING)
- round-trip via SQLModel: SELECTs return rows shaped identically to
  the Pydantic shadow fixtures
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import NullPool
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import select

from db import sample_data as sd
from models import ApiUsage, Application, Job, Profile, User

_DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://naavik:password@127.0.0.1:5433/naavik",
)

_LIVE = os.environ.get("NAAVIK_LIVE_DB", "").strip().lower() in {"1", "true", "yes"}


pytestmark = pytest.mark.skipif(
    not _LIVE,
    reason="set NAAVIK_LIVE_DB=1 (and DATABASE_URL) to run live-DB seed tests",
)


def _fresh_session():
    """Create a fresh engine + sessionmaker per test to avoid event-loop reuse."""
    engine = create_async_engine(_DB_URL, poolclass=NullPool)
    return async_sessionmaker(engine, expire_on_commit=False), engine


async def test_seeded_user_count():
    sm, engine = _fresh_session()
    async with sm() as session:
        users = (await session.scalars(select(User))).all()
        assert len(users) == 1
        assert users[0].email == sd.USER.email
    await engine.dispose()


async def test_seeded_profile():
    sm, engine = _fresh_session()
    async with sm() as session:
        profile = (await session.scalars(select(Profile))).first()
        assert profile is not None
        assert profile.full_name == "Shyam Padia"
        assert profile.work_authorization is not None
    await engine.dispose()


async def test_seeded_jobs():
    sm, engine = _fresh_session()
    async with sm() as session:
        jobs = (await session.scalars(select(Job))).all()
        assert len(jobs) >= 18
        for j in jobs:
            assert 0.0 <= j.score <= 1.0
    await engine.dispose()


async def test_seeded_applications():
    sm, engine = _fresh_session()
    async with sm() as session:
        apps = (await session.scalars(select(Application))).all()
        assert len(apps) == 14
        drafts = [a for a in apps if a.status.value == "DRAFT"]
        assert len(drafts) == 2
        for d in drafts:
            assert d.applied_at is None
    await engine.dispose()


async def test_seeded_api_usage():
    sm, engine = _fresh_session()
    async with sm() as session:
        rows = (await session.scalars(select(ApiUsage))).all()
        assert len(rows) >= 25
        assert all(r.cost_usd >= 0 for r in rows)
    await engine.dispose()


async def test_seed_idempotent():
    """Re-run seed; row counts in tables must not double.

    The summary count from `seed()` is the number of rows the upsert
    *attempted* (one per fixture); ON CONFLICT DO NOTHING skips collisions
    so the actual SELECT count stays stable across re-runs.
    """
    from db.seed import seed

    sm, engine = _fresh_session()
    async with sm() as session:
        before = (await session.scalars(select(User))).all()
        before_count = len(before)

    await seed()
    await seed()

    sm2, engine2 = _fresh_session()
    async with sm2() as session:
        after = (await session.scalars(select(User))).all()
        assert len(after) == before_count
    await engine.dispose()
    await engine2.dispose()


async def test_seeded_user_password_hash_is_real_bcrypt():
    """Plan 10b (item 3): seeded User.password_hash MUST be a real bcrypt hash
    that `verify_password` accepts when given the matching plaintext.

    The CI runner sets `NAAVIK_DEV_PASSWORD` so the credential is stable across
    runs; we read the same env to recover the plaintext for verification.
    """
    from services.auth import verify_password

    expected_password = os.environ.get("NAAVIK_DEV_PASSWORD")
    if not expected_password:
        pytest.skip("NAAVIK_DEV_PASSWORD not set — can't recover the seeded plaintext")

    sm, engine = _fresh_session()
    async with sm() as session:
        user = (await session.scalars(select(User).where(User.id == 1))).first()
        assert user is not None
        # The placeholder bcrypt string from the in-memory shadow must be GONE.
        assert "placeholder.hash.for.dev.password" not in user.password_hash
        # Real bcrypt hash → bcrypt prefix
        assert user.password_hash.startswith("$2b$")
        # And the env-provided plaintext verifies.
        assert verify_password(expected_password, user.password_hash) is True
        # Wrong plaintext fails
        assert verify_password("definitely-not-the-pw", user.password_hash) is False
    await engine.dispose()


# ── Plan 10c (10c.3a) — dev-credentials file ────────────────────────────


async def test_seed_writes_dev_credentials_when_generated_in_debug_mode(monkeypatch, tmp_path):
    """When `dev_password_source == "generated"` AND `app_settings.debug` is
    True AND the seeded Settings are SELF_HOSTED, `db.seed.seed()` MUST
    persist `<data_dir>/dev-credentials` at mode 0600 with the canonical
    two-line format.

    Plan 10c (10c.3a, 2026-05-11). Live-DB test — the User row must NOT
    already exist (the file is only written on a fresh-seed path), so we
    drop everything via downgrade/upgrade through alembic before seeding.
    """
    import stat

    from config import settings as app_settings
    from db import seed as seed_mod

    # Use a tmp_path so the test doesn't write into the operator's
    # `./.naavik/dev-credentials` mid-development.
    monkeypatch.setattr(app_settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(app_settings, "debug", True)

    # Force the generated-password code path even if NAAVIK_DEV_PASSWORD is
    # set in the CI environment (which it usually is for stable creds).
    monkeypatch.delenv("NAAVIK_DEV_PASSWORD", raising=False)

    # Wipe every seeded row so seed() takes the fresh-user branch + writes
    # the file. We delete in reverse dependency order to dodge FK violations.
    from sqlalchemy import text

    sm, engine = _fresh_session()
    async with sm() as session:
        await session.execute(text('TRUNCATE TABLE "user" RESTART IDENTITY CASCADE'))
        await session.commit()
    await engine.dispose()

    await seed_mod.seed()

    creds_path = tmp_path / "dev-credentials"
    assert creds_path.exists(), f"{creds_path} should exist after generated-mode seed"
    # Mode 0600 — owner-readable only.
    mode = stat.S_IMODE(creds_path.stat().st_mode)
    assert mode == 0o600, f"expected mode 0600, got {oct(mode)}"
    # Canonical two-line format.
    content = creds_path.read_text()
    assert "email: " in content
    assert "password: " in content
    # Email matches the seeded fixture.
    from db import sample_data as sd

    assert f"email: {sd.USER.email}" in content


async def test_seed_skips_dev_credentials_when_password_from_env(monkeypatch, tmp_path):
    """When `NAAVIK_DEV_PASSWORD` is exported, the dev-credentials file MUST
    NOT be written — env-supplied passwords are owned by the operator;
    echoing them back to disk is noise and a security smell.

    Plan 10c (10c.3a, 2026-05-11).
    """
    from sqlalchemy import text

    from config import settings as app_settings
    from db import seed as seed_mod

    monkeypatch.setattr(app_settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(app_settings, "debug", True)
    monkeypatch.setenv("NAAVIK_DEV_PASSWORD", "test-stable-pw")

    # Fresh slate so seed() takes the fresh-user branch.
    sm, engine = _fresh_session()
    async with sm() as session:
        await session.execute(text('TRUNCATE TABLE "user" RESTART IDENTITY CASCADE'))
        await session.commit()
    await engine.dispose()

    await seed_mod.seed()

    creds_path = tmp_path / "dev-credentials"
    assert not creds_path.exists(), (
        f"{creds_path} must NOT be written when NAAVIK_DEV_PASSWORD is set "
        "(env-supplied creds are operator-owned)"
    )


# ── Plan 18 (PC.6) — must-change flag on generated dev password ─────────


async def test_seed_sets_must_change_password_when_generated(monkeypatch, tmp_path):
    """When `dev_password_source == "generated"`, the seeded User row gets
    `must_change_password=True`. Plan 18 (PC.6, 2026-05-17).
    """
    from sqlalchemy import text

    from config import settings as app_settings
    from db import seed as seed_mod

    monkeypatch.setattr(app_settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(app_settings, "debug", True)
    monkeypatch.delenv("NAAVIK_DEV_PASSWORD", raising=False)

    sm, engine = _fresh_session()
    async with sm() as session:
        await session.execute(text('TRUNCATE TABLE "user" RESTART IDENTITY CASCADE'))
        await session.commit()
    await engine.dispose()

    await seed_mod.seed()

    sm2, engine2 = _fresh_session()
    async with sm2() as session:
        user = (await session.scalars(select(User).where(User.id == 1))).first()
        assert user is not None
        assert user.must_change_password is True
    await engine2.dispose()


async def test_seed_leaves_must_change_unset_when_env_supplied(monkeypatch, tmp_path):
    """When `NAAVIK_DEV_PASSWORD` is exported, the seeded User row gets
    `must_change_password=False` (env-supplied creds are operator-owned).
    Plan 18 (PC.6, 2026-05-17).
    """
    from sqlalchemy import text

    from config import settings as app_settings
    from db import seed as seed_mod

    monkeypatch.setattr(app_settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(app_settings, "debug", True)
    monkeypatch.setenv("NAAVIK_DEV_PASSWORD", "OperatorPicked1234")

    sm, engine = _fresh_session()
    async with sm() as session:
        await session.execute(text('TRUNCATE TABLE "user" RESTART IDENTITY CASCADE'))
        await session.commit()
    await engine.dispose()

    await seed_mod.seed()

    sm2, engine2 = _fresh_session()
    async with sm2() as session:
        user = (await session.scalars(select(User).where(User.id == 1))).first()
        assert user is not None
        assert user.must_change_password is False
    await engine2.dispose()
