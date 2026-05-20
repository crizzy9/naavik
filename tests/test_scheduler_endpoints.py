"""Plan 47 (0.2.0.10a) — operator scheduler endpoints.

Tests the 4-endpoint router at `/api/v1/scheduler/*`:

  - GET  /jobs               (list registered jobs)
  - POST /jobs/{id}/run      (transient DateTrigger add_job; preserves cron)
  - POST /jobs/{id}/pause    (scheduler.pause_job → snapshot)
  - POST /jobs/{id}/resume   (scheduler.resume_job → snapshot)

Auth bypass mirrors `tests/test_discover_csrf.py:60` — `require_authed_session`
dep override returns None so we exercise the CSRF gate + scheduler ops in
isolation. Scheduler handle patched via `monkeypatch.setattr(scheduler.api_module, "get_scheduler", ...)`
so each test runs against a stable `_FakeScheduler` namespace rather than the
real `_SCHEDULER` global from `src/scheduler/__init__.py`.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
from apscheduler.jobstores.base import JobLookupError

# bcrypt cost low for test isolation (mirrors test_auth.py / test_discover_csrf.py).
os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")
# Memory persistence keeps the matching-CSRF path away from Postgres — this
# router doesn't touch DB but `TestClient(app)` fires the lifespan otherwise.
os.environ["NAAVIK_PERSISTENCE"] = "memory"


# ── _FakeJob + _FakeScheduler ───────────────────────────────────────────


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
        # The router calls `str(job.trigger)`; emulate that via __str__.
        class _T:
            def __str__(_self) -> str:  # noqa: N805
                return self.trigger_str

        return _T()


class _FakeScheduler:
    """In-memory APScheduler stand-in. Captures pause/resume/add_job calls."""

    def __init__(self, *, running: bool = True) -> None:
        self.running = running
        self._jobs: dict[str, _FakeJob] = {}
        self.add_job_calls: list[dict] = []
        self.pause_calls: list[str] = []
        self.resume_calls: list[str] = []

    def add_existing(self, job: _FakeJob) -> None:
        self._jobs[job.id] = job

    def get_jobs(self) -> list[_FakeJob]:
        return list(self._jobs.values())

    def get_job(self, job_id: str) -> _FakeJob | None:
        if job_id not in self._jobs:
            raise JobLookupError(job_id)
        return self._jobs[job_id]

    def pause_job(self, job_id: str) -> None:
        if job_id not in self._jobs:
            raise JobLookupError(job_id)
        self.pause_calls.append(job_id)
        self._jobs[job_id].next_run_time = None

    def resume_job(self, job_id: str) -> None:
        if job_id not in self._jobs:
            raise JobLookupError(job_id)
        self.resume_calls.append(job_id)
        # Snap forward to a fixed sentinel so the test can assert paused=False.
        self._jobs[job_id].next_run_time = datetime(2030, 1, 1, tzinfo=UTC)

    def add_job(self, func, trigger, *, id, name, **kwargs):  # noqa: A002
        self.add_job_calls.append(
            {"func": func, "trigger": trigger, "id": id, "name": name, **kwargs}
        )
        # Materialize so a follow-up get_job() (if needed) works.
        self._jobs[id] = _FakeJob(
            id=id,
            name=name,
            next_run_time=datetime.now(UTC),
            trigger_str=str(trigger),
            max_instances=kwargs.get("max_instances", 1),
            coalesce=kwargs.get("coalesce", True),
            func=func,
        )


# ── Test client + scheduler patching ────────────────────────────────────


def _build_client(monkeypatch: pytest.MonkeyPatch, fake: _FakeScheduler | None):
    """Spin up the full FastAPI app, override auth dep, patch scheduler handle.

    `fake=None` covers the 503 path (scheduler not started).
    """
    from fastapi.testclient import TestClient

    import api.scheduler as router_module
    from main import app
    from services.auth import require_authed_session

    async def _bypass_auth():
        return None

    app.dependency_overrides[require_authed_session] = _bypass_auth
    monkeypatch.setattr(router_module, "get_scheduler", lambda: fake)
    client = TestClient(app, raise_server_exceptions=True)
    return app, client


def _restore(app):
    from services.auth import require_authed_session

    app.dependency_overrides.pop(require_authed_session, None)


def _seed_six_jobs() -> _FakeScheduler:
    fake = _FakeScheduler(running=True)
    for source in (
        "scraping.linkedin",
        "scraping.workday",
        "scraping.greenhouse",
        "scraping.lever",
        "scraping.ashby",
        "scraping.indeed",
    ):
        fake.add_existing(
            _FakeJob(
                id=source,
                name=source,
                next_run_time=datetime(2030, 1, 1, tzinfo=UTC),
                trigger_str=f"cron[{source}]",
            )
        )
    return fake


_MATCHING = "matching-csrf-token-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


# ── 1. List unauth-401 ─────────────────────────────────────────────────


def test_jobs_list_unauthed_401(monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /api/v1/scheduler/jobs without session cookie → 401."""
    from fastapi.testclient import TestClient

    import api.scheduler as router_module
    from main import app

    monkeypatch.setattr(router_module, "get_scheduler", lambda: _seed_six_jobs())
    # No dependency override → require_authed_session runs and returns 401
    # because no naavik_session cookie is present.
    client = TestClient(app, raise_server_exceptions=True)
    r = client.get("/api/v1/scheduler/jobs")
    assert r.status_code == 401


# ── 2. List authed-200 with 6 jobs ─────────────────────────────────────


def test_jobs_list_authed_200(monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /api/v1/scheduler/jobs with auth bypass → 200 + 6 jobs."""
    fake = _seed_six_jobs()
    app, client = _build_client(monkeypatch, fake)
    try:
        r = client.get("/api/v1/scheduler/jobs")
    finally:
        _restore(app)
    assert r.status_code == 200
    body = r.json()
    assert body["running"] is True
    assert len(body["jobs"]) == 6
    ids = {j["id"] for j in body["jobs"]}
    assert ids == {
        "scraping.linkedin",
        "scraping.workday",
        "scraping.greenhouse",
        "scraping.lever",
        "scraping.ashby",
        "scraping.indeed",
    }
    sample = body["jobs"][0]
    assert "trigger" in sample
    assert "next_run_time" in sample
    assert "paused" in sample
    assert sample["paused"] is False


# ── 3. Run unauth-401 ──────────────────────────────────────────────────


def test_run_unauthed_401(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    import api.scheduler as router_module
    from main import app

    monkeypatch.setattr(router_module, "get_scheduler", lambda: _seed_six_jobs())
    client = TestClient(app, raise_server_exceptions=True)
    r = client.post(
        "/api/v1/scheduler/jobs/scraping.linkedin/run",
        cookies={"naavik_csrf": _MATCHING},
        headers={"X-CSRF-Token": _MATCHING},
    )
    assert r.status_code == 401


# ── 4. Run no-CSRF 403 ─────────────────────────────────────────────────


def test_run_no_csrf_403(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /run with auth bypass but mismatched CSRF cookie/header → 403."""
    fake = _seed_six_jobs()
    app, client = _build_client(monkeypatch, fake)
    try:
        r = client.post(
            "/api/v1/scheduler/jobs/scraping.linkedin/run",
            cookies={"naavik_csrf": "cookie-token-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"},
            headers={"X-CSRF-Token": "header-token-cccccccccccccccccccccccccccccc"},
        )
    finally:
        _restore(app)
    assert r.status_code == 403
    assert "CSRF" in r.text or "csrf" in r.text


# ── 5. Run with-CSRF 202 + add_job call captured ───────────────────────


def test_run_with_csrf_202(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _seed_six_jobs()
    app, client = _build_client(monkeypatch, fake)
    try:
        r = client.post(
            "/api/v1/scheduler/jobs/scraping.linkedin/run",
            cookies={"naavik_csrf": _MATCHING},
            headers={"X-CSRF-Token": _MATCHING},
        )
    finally:
        _restore(app)
    assert r.status_code == 202
    body = r.json()
    # queued_job_id matches `scraping.linkedin-manual-<hex8>` shape.
    assert re.fullmatch(r"scraping\.linkedin-manual-[0-9a-f]{8}", body["queued_job_id"])
    assert "scheduled_at" in body
    # add_job was invoked exactly once and the func came from the original job.
    assert len(fake.add_job_calls) == 1
    call = fake.add_job_calls[0]
    assert call["id"] == body["queued_job_id"]
    assert call["max_instances"] == 1
    assert call["coalesce"] is True
    # The transient job should use DateTrigger (now), not the original cron trigger.
    from apscheduler.triggers.date import DateTrigger

    assert isinstance(call["trigger"], DateTrigger)


# ── 6. Pause/resume round-trip ─────────────────────────────────────────


def test_pause_resume_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _seed_six_jobs()
    app, client = _build_client(monkeypatch, fake)
    try:
        pause = client.post(
            "/api/v1/scheduler/jobs/scraping.linkedin/pause",
            cookies={"naavik_csrf": _MATCHING},
            headers={"X-CSRF-Token": _MATCHING},
        )
        resume = client.post(
            "/api/v1/scheduler/jobs/scraping.linkedin/resume",
            cookies={"naavik_csrf": _MATCHING},
            headers={"X-CSRF-Token": _MATCHING},
        )
    finally:
        _restore(app)

    assert pause.status_code == 200
    pause_body = pause.json()
    assert pause_body["id"] == "scraping.linkedin"
    assert pause_body["paused"] is True
    assert pause_body["next_run_time"] is None

    assert resume.status_code == 200
    resume_body = resume.json()
    assert resume_body["id"] == "scraping.linkedin"
    assert resume_body["paused"] is False
    assert resume_body["next_run_time"] is not None

    assert fake.pause_calls == ["scraping.linkedin"]
    assert fake.resume_calls == ["scraping.linkedin"]


# ── 7. Run unknown-job 404 ─────────────────────────────────────────────


def test_run_unknown_job_404(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _seed_six_jobs()
    app, client = _build_client(monkeypatch, fake)
    try:
        r = client.post(
            "/api/v1/scheduler/jobs/scraping.does-not-exist/run",
            cookies={"naavik_csrf": _MATCHING},
            headers={"X-CSRF-Token": _MATCHING},
        )
    finally:
        _restore(app)
    assert r.status_code == 404
    assert "not found" in r.text


# ── 8. Scheduler-not-running 503 ───────────────────────────────────────


def test_jobs_list_scheduler_not_running(monkeypatch: pytest.MonkeyPatch) -> None:
    """When `get_scheduler()` returns None (lifespan failed or test bypass),
    every endpoint surfaces 503 + 'scheduler not started' body."""
    app, client = _build_client(monkeypatch, fake=None)
    try:
        r = client.get("/api/v1/scheduler/jobs")
    finally:
        _restore(app)
    assert r.status_code == 503
    assert "scheduler not started" in r.text


# ── 9. Pause unknown-job 404 (parity with run) ─────────────────────────


def test_pause_unknown_job_404(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _seed_six_jobs()
    app, client = _build_client(monkeypatch, fake)
    try:
        r = client.post(
            "/api/v1/scheduler/jobs/scraping.does-not-exist/pause",
            cookies={"naavik_csrf": _MATCHING},
            headers={"X-CSRF-Token": _MATCHING},
        )
    finally:
        _restore(app)
    assert r.status_code == 404
    assert "not found" in r.text
