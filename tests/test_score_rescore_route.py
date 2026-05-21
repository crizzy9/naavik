"""POST /api/v1/jobs/{id}/rescore — plan 65 § D.6 / T10.

Verifies CSRF gate, auth gate, IDOR-via-404, and that the layered
orchestrator is invoked + result persisted.
"""

from __future__ import annotations

import os

os.environ.setdefault("NAAVIK_DEBUG", "1")
os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")

from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402


def _build_client(*, user_id: int | None = 1):
    from main import app
    from services.auth import require_authed_session

    async def _stub_auth():
        if user_id is None:
            return None
        return MagicMock(id=user_id)

    app.dependency_overrides[require_authed_session] = _stub_auth
    client = TestClient(app, raise_server_exceptions=True)
    return app, client


def _restore(app):
    from services.auth import require_authed_session

    app.dependency_overrides.pop(require_authed_session, None)


def test_rescore_rejects_mismatched_csrf():
    app, client = _build_client()
    try:
        r = client.post(
            "/api/v1/jobs/1/rescore",
            cookies={"naavik_csrf": "a" * 32},
            headers={"X-CSRF-Token": "b" * 32},
        )
    finally:
        _restore(app)
    assert r.status_code == 403
    assert "csrf" in r.text.lower()


def test_rescore_requires_real_authed_session():
    """Fake-session callers (user_id=None) get 401 — rescore is real-auth only."""
    app, client = _build_client(user_id=None)
    matching = "match-tok-cccccccccccccccccccccccccccccccc"
    try:
        r = client.post(
            "/api/v1/jobs/1/rescore",
            cookies={"naavik_csrf": matching},
            headers={"X-CSRF-Token": matching},
        )
    finally:
        _restore(app)
    assert r.status_code == 401


def test_rescore_returns_404_when_job_missing():
    """When the live-DB Job lookup returns None → 404."""
    app, client = _build_client(user_id=1)
    matching = "match-tok-cccccccccccccccccccccccccccccccc"

    async def _empty_exec(*args, **kwargs):
        return MagicMock(one_or_none=lambda: None, all=lambda: [])

    fake_session = MagicMock()
    fake_session.exec = AsyncMock(side_effect=_empty_exec)
    fake_session.commit = AsyncMock()

    from db.session import get_session

    async def _stub_session():
        yield fake_session

    app.dependency_overrides[get_session] = _stub_session
    try:
        r = client.post(
            "/api/v1/jobs/9999/rescore",
            cookies={"naavik_csrf": matching},
            headers={"X-CSRF-Token": matching},
        )
    finally:
        app.dependency_overrides.pop(get_session, None)
        _restore(app)
    assert r.status_code == 404


def test_rescore_returns_404_on_cross_user_idor():
    """A Job belonging to user 2 returns 404 when requester is user 1."""
    app, client = _build_client(user_id=1)
    matching = "match-tok-cccccccccccccccccccccccccccccccc"

    # First exec: returns the job, but user_id=2.
    other_user_job = MagicMock()
    other_user_job.id = 1
    other_user_job.user_id = 2

    exec_calls = [MagicMock(one_or_none=lambda: other_user_job)]

    async def _exec(*args, **kwargs):
        if exec_calls:
            return exec_calls.pop(0)
        return MagicMock(one_or_none=lambda: None, all=lambda: [])

    fake_session = MagicMock()
    fake_session.exec = AsyncMock(side_effect=_exec)
    fake_session.commit = AsyncMock()

    from db.session import get_session

    async def _stub_session():
        yield fake_session

    app.dependency_overrides[get_session] = _stub_session
    try:
        r = client.post(
            "/api/v1/jobs/1/rescore",
            cookies={"naavik_csrf": matching},
            headers={"X-CSRF-Token": matching},
        )
    finally:
        app.dependency_overrides.pop(get_session, None)
        _restore(app)
    assert r.status_code == 404


def test_rescore_happy_path_calls_orchestrator():
    """Owned job + profile + settings present → orchestrator fires → 200."""
    app, client = _build_client(user_id=1)
    matching = "match-tok-cccccccccccccccccccccccccccccccc"

    # Build a JobRead-projectable Job mock.
    from datetime import UTC, datetime

    from models import Job, Profile, Settings

    job = Job(
        id=1,
        user_id=1,
        source="linkedin",
        board="linkedin",
        external_id="manual-x",
        url="https://example.com/job",
        url_type="job",
        company="Acme",
        role="SWE",
        description="Build things",
        score=0.0,
        tags=["ai-ml"],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    profile = Profile(
        id=10,
        user_id=1,
        full_name="Shyam",
        headline="SWE",
        email="s@example.com",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    settings = Settings(
        user_id=1,
        semantic_match_enabled=False,
        llm_model="claude-3.5-sonnet-20250219",
    )

    exec_calls = [
        MagicMock(one_or_none=lambda: job),  # Job lookup
        MagicMock(one_or_none=lambda: profile),  # Profile lookup
        MagicMock(one_or_none=lambda: settings),  # Settings lookup
    ]

    async def _exec(*args, **kwargs):
        if exec_calls:
            return exec_calls.pop(0)
        return MagicMock(one_or_none=lambda: None, all=lambda: [])

    fake_session = MagicMock()
    fake_session.exec = AsyncMock(side_effect=_exec)
    fake_session.commit = AsyncMock()
    fake_session.add = MagicMock()
    fake_session.flush = AsyncMock()

    from db.session import get_session

    async def _stub_session():
        yield fake_session

    app.dependency_overrides[get_session] = _stub_session

    # Stub the orchestrator to a no-op; the route just needs to call it.
    async def _stub_score(*args, **kwargs):
        from llm.prompts.score_job import JobScore

        return JobScore(score=0.42, explanation="ok")

    try:
        with patch(
            "services.scorer.orchestrator.score_job_layered",
            new=_stub_score,
        ):
            r = client.post(
                "/api/v1/jobs/1/rescore",
                cookies={"naavik_csrf": matching},
                headers={"X-CSRF-Token": matching},
            )
    finally:
        app.dependency_overrides.pop(get_session, None)
        _restore(app)
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == 1
