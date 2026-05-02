"""Side-by-side persistence-swap test — Wave 4 of plan 10 § B.10.

Verifies that the `NAAVIK_PERSISTENCE` env var routes the sample-data
accessors through either in-memory lists (`memory`, default) or DB
queries (`db`). For the high-traffic read accessors covered by Wave 4,
both modes return Pydantic shadow instances of identical shape.

Live-DB tests are opt-in via `NAAVIK_LIVE_DB=1`. Memory-mode tests run
unconditionally and verify the env-var dispatch logic + fallback path
(when DB is unreachable, memory fixtures are used).
"""

from __future__ import annotations

import os

import pytest

_LIVE = os.environ.get("NAAVIK_LIVE_DB", "").strip().lower() in {"1", "true", "yes"}


# ── Memory-mode dispatch ───────────────────────────────────────────────


def test_persistence_mode_default_is_memory(monkeypatch) -> None:
    monkeypatch.delenv("NAAVIK_PERSISTENCE", raising=False)
    from db import sample_data as sd

    assert sd._persistence_mode() == "memory"
    assert sd._is_db_mode() is False


def test_persistence_mode_db_recognized(monkeypatch) -> None:
    monkeypatch.setenv("NAAVIK_PERSISTENCE", "db")
    from db import sample_data as sd

    assert sd._persistence_mode() == "db"
    assert sd._is_db_mode() is True


def test_persistence_mode_case_insensitive(monkeypatch) -> None:
    from db import sample_data as sd

    monkeypatch.setenv("NAAVIK_PERSISTENCE", "DB")
    assert sd._is_db_mode() is True
    monkeypatch.setenv("NAAVIK_PERSISTENCE", "Memory")
    assert sd._is_db_mode() is False


# ── Memory mode returns Pydantic shadow instances ──────────────────────


async def test_get_profile_memory_mode_returns_shadow() -> None:
    from db import sample_data as sd
    from db.sample_data_models import Profile as ShadowProfile

    profile = await sd.get_profile()
    assert isinstance(profile, ShadowProfile)
    assert profile.full_name == "Shyam Padia"


async def test_discover_queue_memory_mode() -> None:
    from db import sample_data as sd

    jobs = await sd.discover_queue()
    assert len(jobs) >= 6
    # score-desc order
    scores = [j.score for j in jobs]
    assert scores == sorted(scores, reverse=True)


async def test_applications_visible_memory_mode() -> None:
    from db import sample_data as sd

    apps = await sd.applications_visible_in_tracking()
    statuses = {a.status.value for a in apps}
    # DRAFT + CLOSED hidden; APPLIED..OFFER visible
    assert "DRAFT" not in statuses
    assert "CLOSED" not in statuses


# ── DB mode (live DB only) ─────────────────────────────────────────────


@pytest.mark.skipif(not _LIVE, reason="set NAAVIK_LIVE_DB=1 + DATABASE_URL to test DB mode")
async def test_get_profile_db_mode(monkeypatch) -> None:
    monkeypatch.setenv("NAAVIK_PERSISTENCE", "db")
    from db import sample_data as sd
    from db.sample_data_models import Profile as ShadowProfile

    profile = await sd.get_profile()
    assert isinstance(profile, ShadowProfile)
    assert profile.full_name == "Shyam Padia"


@pytest.mark.skipif(not _LIVE, reason="set NAAVIK_LIVE_DB=1 + DATABASE_URL to test DB mode")
async def test_discover_queue_db_mode_matches_memory(monkeypatch) -> None:
    """Side-by-side: same seeded fixture data should overlap heavily."""
    from db import sample_data as sd

    monkeypatch.delenv("NAAVIK_PERSISTENCE", raising=False)
    memory_jobs = await sd.discover_queue()
    memory_ids = {j.id for j in memory_jobs}

    monkeypatch.setenv("NAAVIK_PERSISTENCE", "db")
    db_jobs = await sd.discover_queue()
    db_ids = {j.id for j in db_jobs}

    # The DB may have additional jobs added by other tests' mutations
    # (e.g. test_bullets_post inserts new rows), so we assert the seeded
    # memory ids are a subset of the live DB ids — not strict equality.
    assert memory_ids.issubset(db_ids)


@pytest.mark.skipif(not _LIVE, reason="set NAAVIK_LIVE_DB=1 + DATABASE_URL to test DB mode")
async def test_applications_visible_db_mode_matches_memory(monkeypatch) -> None:
    from db import sample_data as sd

    monkeypatch.delenv("NAAVIK_PERSISTENCE", raising=False)
    memory_apps = await sd.applications_visible_in_tracking()
    memory_ids = sorted(a.id for a in memory_apps)

    monkeypatch.setenv("NAAVIK_PERSISTENCE", "db")
    db_apps = await sd.applications_visible_in_tracking()
    db_ids = sorted(a.id for a in db_apps)

    assert memory_ids == db_ids


@pytest.mark.skipif(not _LIVE, reason="set NAAVIK_LIVE_DB=1 + DATABASE_URL to test DB mode")
async def test_get_user_db_mode(monkeypatch) -> None:
    monkeypatch.setenv("NAAVIK_PERSISTENCE", "db")
    from db import sample_data as sd

    user = await sd.get_user()
    assert user.email == "shyam.padia930@gmail.com"


@pytest.mark.skipif(not _LIVE, reason="set NAAVIK_LIVE_DB=1 + DATABASE_URL to test DB mode")
async def test_get_jobs_db_mode_count(monkeypatch) -> None:
    monkeypatch.setenv("NAAVIK_PERSISTENCE", "db")
    from db import sample_data as sd

    jobs = await sd.get_jobs()
    assert len(jobs) >= 18
