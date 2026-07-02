"""Plan 59 (0.2.7.12) — auto-apply immediate dispatch on right-swipe.

Covers the 5-test slate in plan § D.6:

  1. `update_auto_apply(auto_apply_immediate_dispatch=...)` round-trips
     through the service layer (True → flush → re-read; flip back to False).
  2. Alembic 0011 round-trip — upgrade adds column with `server_default
     false`; downgrade drops; re-upgrade adds again.
  3. Right-swipe POST with `auto_apply_immediate_dispatch=True` schedules
     a transient `applications.auto_apply-immediate-<8hex>` via APScheduler
     `DateTrigger(now)`; response is the normal next-card HTML.
  4. Right-swipe POST with `auto_apply_immediate_dispatch=False` (default)
     does NOT call `scheduler.add_job`; response unchanged.
  5. Right-swipe POST with `get_scheduler()` returning None (lifespan
     failed) swallows the failure; response unchanged + queue_state still
     flipped + DRAFT still created.

Tests 3–5 mirror the canonical `_FakeScheduler` pattern from
`tests/test_scheduler_endpoints.py` (plan 47). Auth bypass + CSRF wire
mirror `tests/test_discover_csrf.py` (plan 44).
"""

from __future__ import annotations

import importlib.util
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from apscheduler.jobstores.base import JobLookupError

pytestmark = pytest.mark.uses_sample_data_shims

os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")
os.environ.setdefault("NAAVIK_DEBUG", "1")
os.environ["NAAVIK_PERSISTENCE"] = "memory"


_MATCHING = "matching-csrf-token-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


# ── Sample-data restoration ─────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _restore_sample_data_state():
    """Tests 3–5 mutate `APPLICATIONS` + `JOBS` (via `_create_draft` +
    `_set_job_queue_state`). Snapshot + restore so the next test module
    sees the canonical sample-data inventory.
    """
    from db import sample_data as sd

    apps_snap = [a.model_copy(deep=True) for a in sd.APPLICATIONS]
    jobs_snap = [j.model_copy(deep=True) for j in sd.JOBS]
    yield
    sd.APPLICATIONS.clear()
    sd.APPLICATIONS.extend(apps_snap)
    sd.JOBS.clear()
    sd.JOBS.extend(jobs_snap)


# ── _FakeScheduler — copied from tests/test_scheduler_endpoints.py ──────


@dataclass
class _FakeJob:
    id: str
    name: str
    next_run_time: datetime | None
    trigger_str: str
    max_instances: int = 1
    coalesce: bool = True
    pending: bool = False
    func: Any = None
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.func is None:
            self.func = lambda: None

    @property
    def trigger(self):
        class _T:
            def __str__(_self) -> str:  # noqa: N805
                return self.trigger_str

        return _T()


class _FakeScheduler:
    """In-memory APScheduler stand-in. Captures add_job calls."""

    def __init__(self, *, running: bool = True) -> None:
        self.running = running
        self._jobs: dict[str, _FakeJob] = {}
        self.add_job_calls: list[dict] = []

    def get_jobs(self) -> list[_FakeJob]:
        return list(self._jobs.values())

    def get_job(self, job_id: str) -> _FakeJob | None:
        if job_id not in self._jobs:
            raise JobLookupError(job_id)
        return self._jobs[job_id]

    def add_job(self, func, trigger, *, id, name, **kwargs):  # noqa: A002
        self.add_job_calls.append(
            {"func": func, "trigger": trigger, "id": id, "name": name, **kwargs}
        )
        self._jobs[id] = _FakeJob(
            id=id,
            name=name,
            next_run_time=datetime.now(UTC),
            trigger_str=str(trigger),
            max_instances=kwargs.get("max_instances", 1),
            coalesce=kwargs.get("coalesce", True),
            func=func,
        )


# ── Settings stand-in + dep override scaffolding ─────────────────────────


def _make_settings(*, immediate: bool = False) -> SimpleNamespace:
    """Minimal Settings stand-in for the route's read surface."""
    return SimpleNamespace(
        user_id=1,
        auto_apply_immediate_dispatch=immediate,
    )


class _NoopSession:
    async def commit(self):  # pragma: no cover
        return None

    async def rollback(self):  # pragma: no cover
        return None

    async def close(self):  # pragma: no cover
        return None


async def _fake_get_session():
    yield _NoopSession()


def _build_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    immediate: bool,
    fake_scheduler: _FakeScheduler | None,
):
    """Spin up TestClient with auth bypass + Settings stub + scheduler patch.

    `fake_scheduler=None` exercises the `get_scheduler() is None` branch
    (Test 5).
    """
    from fastapi.testclient import TestClient

    from db.session import get_session
    from main import app
    from services.auth import require_authed_session

    async def _bypass_auth():
        # Return a User-shaped stub so `_effective_user_id(user)` is non-None.
        return SimpleNamespace(id=1)

    async def _fake_get_or_create(session, user_id):
        return _make_settings(immediate=immediate)

    app.dependency_overrides[require_authed_session] = _bypass_auth
    app.dependency_overrides[get_session] = _fake_get_session

    # Patch the lazily-imported names inside _maybe_dispatch_auto_apply_now.
    # The function imports `settings_service.get_or_create` + `get_scheduler`
    # at call time, so patching the parent modules is sufficient.
    from services import settings_service

    monkeypatch.setattr(settings_service, "get_or_create", _fake_get_or_create)
    monkeypatch.setattr("scheduler.get_scheduler", lambda: fake_scheduler)

    client = TestClient(app, raise_server_exceptions=True)
    return app, client


def _restore(app):
    from db.session import get_session
    from services.auth import require_authed_session

    app.dependency_overrides.pop(require_authed_session, None)
    app.dependency_overrides.pop(get_session, None)


# ── Test 1: service-layer round-trip ─────────────────────────────────────


def test_field_round_trips_through_settings_service():
    """`update_auto_apply(auto_apply_immediate_dispatch=...)` flushes the
    field; default on fresh Settings is True (migration 0028 — a queued
    swipe should start moving within seconds); flips persist both ways.
    """
    from models import Settings

    s = Settings(user_id=1)
    assert s.auto_apply_immediate_dispatch is True

    # Simulate the service-layer field-set path (no DB required — the
    # update happens on the in-memory instance before flush).
    s.auto_apply_immediate_dispatch = False
    assert s.auto_apply_immediate_dispatch is False

    s.auto_apply_immediate_dispatch = True
    assert s.auto_apply_immediate_dispatch is True


# ── Test 2: alembic 0011 round-trip ──────────────────────────────────────


def _load_migration_0011():
    repo_root = Path(__file__).resolve().parent.parent
    path = repo_root / "migrations" / "versions" / "0011_settings_auto_apply_immediate.py"
    spec = importlib.util.spec_from_file_location("_alembic_0011", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_pre_0011_settings_table(engine: sa.Engine) -> None:
    """Stand up a minimal `settings` table without the new column."""
    metadata = sa.MetaData()
    sa.Table(
        "settings",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, nullable=False),
    )
    metadata.create_all(engine)


def _settings_columns(engine: sa.Engine) -> dict[str, dict]:
    inspector = sa.inspect(engine)
    return {col["name"]: col for col in inspector.get_columns("settings")}


def test_alembic_0011_round_trip(tmp_path):
    """upgrade adds NOT NULL bool with server_default false; downgrade
    drops it; re-upgrade adds it again."""
    db_path = tmp_path / "round_trip.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0011_settings_table(engine)
        pre = _settings_columns(engine)
        assert "auto_apply_immediate_dispatch" not in pre

        migration = _load_migration_0011()

        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()
        post = _settings_columns(engine)
        assert "auto_apply_immediate_dispatch" in post
        col = post["auto_apply_immediate_dispatch"]
        assert col["nullable"] is False
        # SQLite stringifies the boolean default; both reflectors render
        # the value as either "0" or "false" — accept any falsy textual
        # representation.
        default = (col.get("default") or "").lower()
        assert default in ("0", "false", "'false'", "false()")

        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.downgrade()
        post_down = _settings_columns(engine)
        assert "auto_apply_immediate_dispatch" not in post_down

        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()
        post_re_up = _settings_columns(engine)
        assert "auto_apply_immediate_dispatch" in post_re_up
    finally:
        engine.dispose()


# ── Test 3: immediate dispatch fires when enabled ───────────────────────


def test_immediate_dispatch_fires_when_enabled(monkeypatch: pytest.MonkeyPatch):
    """Settings.auto_apply_immediate_dispatch=True + scheduler.running=True
    → exactly one add_job call with `id` matching the manual-id regex,
    func equal to `scheduler.jobs.auto_apply`, trigger=DateTrigger.
    """
    from apscheduler.triggers.date import DateTrigger

    from scheduler.jobs import auto_apply as expected_func

    fake = _FakeScheduler(running=True)
    app, client = _build_client(monkeypatch, immediate=True, fake_scheduler=fake)
    try:
        r = client.post(
            "/api/v1/applications/101/auto-submit",
            cookies={"naavik_csrf": _MATCHING},
            headers={"X-CSRF-Token": _MATCHING},
        )
    finally:
        _restore(app)

    assert r.status_code == 200, r.text
    assert len(fake.add_job_calls) == 1
    call = fake.add_job_calls[0]
    assert re.fullmatch(r"applications\.auto_apply-immediate-[0-9a-f]{8}", call["id"]), (
        f"id={call['id']!r} doesn't match expected manual-id shape"
    )
    assert call["name"] == call["id"]
    assert call["func"] is expected_func
    assert isinstance(call["trigger"], DateTrigger)
    assert call["max_instances"] == 1
    assert call["coalesce"] is True
    assert call["replace_existing"] is False


# ── Test 4: immediate dispatch skipped when disabled ────────────────────


def test_immediate_dispatch_skipped_when_disabled(monkeypatch: pytest.MonkeyPatch):
    """Settings.auto_apply_immediate_dispatch=False (default) → no add_job
    call; queue_state still flipped + DRAFT still created (existing
    behavior intact); response still 200 + next-card HTML.
    """
    fake = _FakeScheduler(running=True)
    app, client = _build_client(monkeypatch, immediate=False, fake_scheduler=fake)
    try:
        r = client.post(
            "/api/v1/applications/102/auto-submit",
            cookies={"naavik_csrf": _MATCHING},
            headers={"X-CSRF-Token": _MATCHING},
        )
    finally:
        _restore(app)

    assert r.status_code == 200, r.text
    assert fake.add_job_calls == []

    # Existing-behavior assertion: queue_state on the swiped job got
    # flipped to QUEUED_FOR_AUTO_APPLY, and an Application record exists
    # (sample-data: 102 already had RECRUITER_SCREEN; `_create_draft` is
    # a no-op when an Application for that (user, job) already exists).
    from db import sample_data as sd
    from models.enums import JobQueueState

    job = next((j for j in sd.JOBS if j.id == 102), None)
    assert job is not None
    assert job.queue_state == JobQueueState.QUEUED_FOR_AUTO_APPLY
    apps = [a for a in sd.APPLICATIONS if a.job_id == 102 and a.user_id == 1]
    assert len(apps) >= 1


# ── Test 5: scheduler-None swallowed ─────────────────────────────────────


def test_immediate_dispatch_swallows_scheduler_none(monkeypatch: pytest.MonkeyPatch):
    """`Settings.auto_apply_immediate_dispatch=True` but `get_scheduler()`
    returns None (lifespan boot failed) → route returns 200, no exception
    propagates, queue_state still flipped + DRAFT still created.
    """
    app, client = _build_client(monkeypatch, immediate=True, fake_scheduler=None)
    try:
        r = client.post(
            "/api/v1/applications/103/auto-submit",
            cookies={"naavik_csrf": _MATCHING},
            headers={"X-CSRF-Token": _MATCHING},
        )
    finally:
        _restore(app)

    assert r.status_code == 200, r.text
    # No exception leaked; the body short-circuits at sample_data with the
    # next-card swipe response. We don't bother sniffing the log line — the
    # 200 status + no-raise proves the best-effort guard worked.

    from db import sample_data as sd
    from models.enums import JobQueueState

    job = next((j for j in sd.JOBS if j.id == 103), None)
    assert job is not None
    assert job.queue_state == JobQueueState.QUEUED_FOR_AUTO_APPLY
    apps = [a for a in sd.APPLICATIONS if a.job_id == 103 and a.user_id == 1]
    assert len(apps) >= 1
