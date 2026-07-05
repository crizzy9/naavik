"""Background bundle-generation dispatch (services/generation_dispatch).

Pins the fast-open contract:
- GET /discover/{id} must never generate inline; drafts land in GENERATING
  and the workspace polls `/_fragments/discover/workspace/{id}`.
- Stale GENERATING rows (orphaned by a restart) are treated as failed.
- spawn_generation dedupes in-flight tasks and honors the test kill-switch.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from models import Application, DocsState
from services.generation import dispatch as generation_dispatch


def _app(docs_state: DocsState, *, updated_ago: timedelta | None = None) -> Application:
    return Application(
        id=1,
        user_id=1,
        job_id=1,
        company="Acme",
        role="Engineer",
        status="DRAFT",
        docs_state=docs_state,
        updated_at=(datetime.now(UTC) - updated_ago) if updated_ago else datetime.now(UTC),
    )


def test_stale_generating_detected():
    stale = _app(DocsState.GENERATING, updated_ago=timedelta(minutes=10))
    assert generation_dispatch.is_generation_stale(stale) is True


def test_fresh_generating_not_stale():
    fresh = _app(DocsState.GENERATING, updated_ago=timedelta(seconds=30))
    assert generation_dispatch.is_generation_stale(fresh) is False


def test_non_generating_states_never_stale():
    for state in (DocsState.NONE, DocsState.READY, DocsState.FAILED, DocsState.STALE):
        assert (
            generation_dispatch.is_generation_stale(_app(state, updated_ago=timedelta(days=1)))
            is False
        )


def test_spawn_disabled_by_kill_switch():
    # conftest's autouse fixture sets enabled=False for every test.
    assert generation_dispatch.enabled is False
    assert generation_dispatch.spawn_generation(999) is False
    assert 999 not in generation_dispatch._tasks


@pytest.mark.asyncio
async def test_mark_generating_flips_state_and_stamps_updated_at():
    class _S:
        def add(self, obj):
            self.added = obj

        async def flush(self):
            return None

    app = _app(DocsState.NONE)
    before = app.updated_at
    session = _S()
    await generation_dispatch.mark_generating(session, app)
    assert app.docs_state == DocsState.GENERATING
    assert app.updated_at >= before


@pytest.mark.uses_sample_data_shims
def test_workspace_poll_fragment_renders():
    """`/_fragments/discover/workspace/{job_id}` returns the workspace subtree
    (the swap root `#review-workspace`), never a full page."""
    from db import sample_data as sd
    from main import app as fastapi_app

    client = TestClient(fastapi_app, raise_server_exceptions=True)
    job = sd.JOBS[0]
    r = client.get(
        f"/_fragments/discover/workspace/{job.id}",
        cookies={"naavik_session": "fake-1"},
    )
    assert r.status_code == 200
    assert 'id="review-workspace"' in r.text
    assert "<html" not in r.text.lower()
