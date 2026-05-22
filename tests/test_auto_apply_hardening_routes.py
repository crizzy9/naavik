"""Route tests for plan 78 auto-apply hardening surfaces.

Covers:
- PUT /api/v1/settings/auto-apply form path: per-board caps + dry-run toggle
- POST /api/v1/settings/auto-apply/drain-queue
- POST /_fragments/discover/{job_id}/pause-auto-apply
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.uses_sample_data_shims

# Matching CSRF pair — mirrors tests/test_stub_endpoints.py.
_CSRF_TOKEN = "csrf-cookie-token-aaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_CSRF_HEADERS = {"X-CSRF-Token": _CSRF_TOKEN}


@pytest.fixture(scope="module")
def client() -> TestClient:
    from main import app

    c = TestClient(app, raise_server_exceptions=True)
    c.cookies.set("naavik_session", "fake-1")
    c.cookies.set("naavik_csrf", _CSRF_TOKEN)
    return c


# ── PUT /api/v1/settings/auto-apply form path ─────────────────────────


def test_put_auto_apply_form_persists_per_board_caps(client, monkeypatch):
    """Form-encoded PUT with `<board>_cap` fields collapses into the JSONB dict."""
    captured: dict = {}

    async def fake_update(session, user_id, **kwargs):
        captured.update(kwargs)

        class _S:
            auto_apply_enabled = True
            auto_apply_score_threshold = 0.85
            auto_apply_daily_cap = None
            eager_review_generation = True
            daily_llm_cost_cap_usd = None
            auto_apply_immediate_dispatch = False
            auto_apply_per_board_daily_caps = {"linkedin": 2, "lever": 5}
            auto_apply_dry_run = False

        return _S()

    from services import settings_service

    monkeypatch.setattr(settings_service, "update_auto_apply", fake_update)

    r = client.put(
        "/api/v1/settings/auto-apply",
        data={"linkedin_cap": "2", "lever_cap": "5", "ashby_cap": ""},
        headers=_CSRF_HEADERS,
    )
    assert r.status_code == 200
    # Per-board caps assembled into the kwarg the service expects.
    assert captured["auto_apply_per_board_daily_caps"] == {"linkedin": 2, "lever": 5}


def test_put_auto_apply_form_dry_run_toggle(client, monkeypatch):
    """Form payload with `auto_apply_dry_run=on` flips the toggle."""
    captured: dict = {}

    async def fake_update(session, user_id, **kwargs):
        captured.update(kwargs)

        class _S:
            auto_apply_enabled = True
            auto_apply_score_threshold = 0.85
            auto_apply_daily_cap = None
            eager_review_generation = True
            daily_llm_cost_cap_usd = None
            auto_apply_immediate_dispatch = False
            auto_apply_per_board_daily_caps = {}
            auto_apply_dry_run = True

        return _S()

    from services import settings_service

    monkeypatch.setattr(settings_service, "update_auto_apply", fake_update)
    r = client.put(
        "/api/v1/settings/auto-apply",
        data={"auto_apply_dry_run": "on"},
        headers=_CSRF_HEADERS,
    )
    assert r.status_code == 200
    assert captured["auto_apply_dry_run"] is True


def test_put_auto_apply_json_path_unchanged_for_existing_callers(client, monkeypatch):
    """JSON path still works for partial PUTs not touching the new fields."""
    captured: dict = {}

    async def fake_update(session, user_id, **kwargs):
        captured.update(kwargs)

        class _S:
            auto_apply_enabled = True
            auto_apply_score_threshold = 0.9
            auto_apply_daily_cap = 10
            eager_review_generation = True
            daily_llm_cost_cap_usd = None
            auto_apply_immediate_dispatch = False
            auto_apply_per_board_daily_caps = {}
            auto_apply_dry_run = False

        return _S()

    from services import settings_service

    monkeypatch.setattr(settings_service, "update_auto_apply", fake_update)
    r = client.put(
        "/api/v1/settings/auto-apply",
        json={"auto_apply_enabled": True, "auto_apply_score_threshold": 0.9},
        headers=_CSRF_HEADERS,
    )
    assert r.status_code == 200
    # New fields stay None (skip) when JSON caller doesn't send them.
    assert captured.get("auto_apply_per_board_daily_caps") is None
    assert captured.get("auto_apply_dry_run") is None


# ── POST /api/v1/settings/auto-apply/drain-queue ──────────────────────


def test_drain_queue_returns_drained_count(client, monkeypatch):
    """Drain endpoint forwards to drain_auto_apply_queue + returns count."""

    async def fake_drain(session, *, user_id, reason=None):
        assert user_id == 1
        assert reason == "settings_drain"
        return 3

    from services import application_service

    monkeypatch.setattr(application_service, "drain_auto_apply_queue", fake_drain)

    r = client.post(
        "/api/v1/settings/auto-apply/drain-queue",
        headers=_CSRF_HEADERS,
    )
    assert r.status_code == 200
    assert r.json() == {"drained": 3}


def test_drain_queue_csrf_required(client, monkeypatch):
    """Drain endpoint requires CSRF header."""
    from fastapi.testclient import TestClient

    from main import app

    c = TestClient(app, raise_server_exceptions=False)
    c.cookies.set("naavik_session", "fake-1")
    # Cookie but NO header → CSRF fails.
    c.cookies.set("naavik_csrf", _CSRF_TOKEN)
    r = c.post("/api/v1/settings/auto-apply/drain-queue")
    assert r.status_code in {403, 400, 401, 422}


# ── POST /_fragments/discover/{job_id}/pause-auto-apply ───────────────


def test_pause_auto_apply_returns_next_card_on_success(client, monkeypatch):
    """Per-job pause flips Job → SAVED + returns the next swipe card fragment."""
    from types import SimpleNamespace

    from models import JobQueueState

    async def fake_pause(session, *, user_id, job_id):
        return SimpleNamespace(id=job_id, queue_state=JobQueueState.SAVED)

    from services import application_service

    monkeypatch.setattr(application_service, "pause_auto_apply_for_job", fake_pause)
    r = client.post(
        "/_fragments/discover/42/pause-auto-apply",
        headers=_CSRF_HEADERS,
    )
    assert r.status_code == 200
    # Returns either the next-card fragment or empty-state fragment, both 200 HTML.
    assert r.headers["content-type"].startswith("text/html")


def test_pause_auto_apply_404_when_unknown_job(client, monkeypatch):
    async def fake_pause(session, *, user_id, job_id):
        return None

    from services import application_service

    monkeypatch.setattr(application_service, "pause_auto_apply_for_job", fake_pause)
    r = client.post(
        "/_fragments/discover/9999/pause-auto-apply",
        headers=_CSRF_HEADERS,
    )
    assert r.status_code == 404
