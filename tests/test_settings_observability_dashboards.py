"""Plan 54 / 0.2.5 observability dashboards — route + body-string tests.

Three small dashboards close out the 0.2.5 release-version observability cleanup:

- 0.2.5.02 Submissions tab    — failure-kind aggregates per ATS adapter
- 0.2.5.03 LLM cost-cap widget — daily spend vs Settings.daily_llm_cost_cap_usd
- 0.2.5.04 Scraper-run history — recent JobScrapeRun rows in Sources tab

Per plan § F: each dashboard ships ≥30 LOC of tests. Tests follow the
`_NoopSession` + monkeypatched-service-helper pattern established by plan 49 /
`tests/test_settings_sources_route.py` so the suite stays DB-free.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")


# ── Test substrate ─────────────────────────────────────────────────────


class _NoopSession:
    """Minimum surface for `Depends(get_session)` — real DB ops are stubbed."""

    async def commit(self):  # pragma: no cover
        return None

    async def rollback(self):  # pragma: no cover
        return None

    async def close(self):  # pragma: no cover
        return None


async def _fake_get_session():
    yield _NoopSession()


@pytest.fixture(scope="module")
def client() -> TestClient:
    from main import app

    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture(scope="module")
def auth_cookies() -> dict[str, str]:
    return {"naavik_session": "fake-1"}


@pytest.fixture(autouse=True)
def _patch_route_helpers(monkeypatch):
    """Stub `aggregate_submission_failures`, `today_cost_usd`, and
    `list_recent_scrape_runs` plus the sources-tab `settings_service` +
    `list_recent_scrape_runs_by_source` helpers. Tests override per-case via
    the returned `state` dict.

    Also patches `sd.get_settings` so the LLM cost-cap widget reads the
    test-provided `daily_llm_cost_cap_usd` (LLM tab ctx still sources this
    from `sd.get_settings` per the broader `_ctx_for_tab` invariant).
    """
    from db import sample_data as sd
    from db.session import get_session
    from main import app
    from services import (
        application_service,
        job_service,
        llm_tracker,
        settings_service,
    )

    state: dict = {
        "failures": [],
        "today_cost": 0.0,
        "recent_runs": [],
        # Sources panel helpers (needed because Item 3 lands in the Sources tab).
        "settings": _make_sources_settings(),
        "by_source_runs": {},
    }

    # Capture the real sd.get_settings result once so we can splice
    # `daily_llm_cost_cap_usd` onto a fresh SimpleNamespace each render.
    original_get_settings = sd.get_settings

    async def _fake_failures(session, *, user_id, since_days=30):
        return state["failures"]

    async def _fake_today_cost(session, *, user_id):
        return state["today_cost"]

    async def _fake_recent_runs(session, *, user_id, limit=50):
        return state["recent_runs"][:limit]

    async def _fake_get_or_create(session, *, user_id):
        return state["settings"]

    async def _fake_by_source_runs(session, *, user_id):
        return state["by_source_runs"]

    async def _wrapped_get_settings():
        real = await original_get_settings()
        cap = getattr(state["settings"], "daily_llm_cost_cap_usd", None)
        # Mutating the shadow row in-place is safe — sample_data hands out a
        # singleton per process and tests reset state between functions.
        try:
            real.daily_llm_cost_cap_usd = cap
        except (AttributeError, TypeError):
            return SimpleNamespace(
                llm_provider=real.llm_provider,
                llm_model=real.llm_model,
                deployment_mode=real.deployment_mode,
                daily_llm_cost_cap_usd=cap,
            )
        return real

    monkeypatch.setattr(application_service, "aggregate_submission_failures", _fake_failures)
    monkeypatch.setattr(llm_tracker, "today_cost_usd", _fake_today_cost)
    monkeypatch.setattr(job_service, "list_recent_scrape_runs", _fake_recent_runs)
    monkeypatch.setattr(settings_service, "get_or_create", _fake_get_or_create)
    monkeypatch.setattr(job_service, "list_recent_scrape_runs_by_source", _fake_by_source_runs)
    monkeypatch.setattr(sd, "get_settings", _wrapped_get_settings)
    app.dependency_overrides[get_session] = _fake_get_session
    yield state
    app.dependency_overrides.pop(get_session, None)


def _make_sources_settings(**overrides):
    # Plan 69 (`0.3.3.12`) widened `_ctx_for_tab` to read llm_provider /
    # llm_model / deployment_mode unconditionally; add those defaults so
    # the existing test cases don't break when their SimpleNamespace
    # reaches the tab body.
    from models.enums import DeploymentMode, LLMProvider

    base = {
        "user_id": 1,
        "sources_enabled": {
            "linkedin": True,
            "workday": True,
            "greenhouse": True,
            "lever": True,
            "ashby": True,
            "indeed": False,
        },
        "source_schedules": {},
        "workday_companies": [],
        "linkedin_keywords": None,
        "linkedin_location": None,
        "indeed_keywords": None,
        "indeed_location": None,
        "scraper_rate_limits": {},
        "daily_llm_cost_cap_usd": None,
        "llm_provider": LLMProvider.ANTHROPIC,
        "llm_model": "claude-3.5-sonnet-20250219",
        "deployment_mode": DeploymentMode.SELF_HOSTED,
        # Plan 61 (`0.2.7.14` / `0.2.7.16`): semantic-match template partial
        # reads these unconditionally; default OFF.
        "semantic_match_enabled": False,
        "semantic_match_threshold": 0.65,
        "embedding_provider": None,
        "semantic_match_sync_on_upsert": False,
        # Other route paths (Sources / Submissions tabs etc.) probe these.
        "auto_apply_enabled": False,
        "auto_apply_score_threshold": 0.85,
        "auto_apply_daily_cap": None,
        "auto_apply_immediate_dispatch": False,
        "auto_apply_adapter_confidence_threshold": 0.7,
        "eager_review_generation": False,
        "consecutive_scrape_failures": {},
        "notify_threshold": 0.80,
        "notify_on_errors": True,
        "notifications_enabled": {},
        "portfolio_cors_allowed_origins": ["https://crypticsoul.dev"],
        "allow_multiple_users": False,
        "jwt_rotation_days": 90,
        "jwt_rotation_grace_days": 7,
        "debug": False,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _make_run(
    *,
    source,
    status_value: str,
    started_minutes_ago: int = 30,
    new_jobs: int = 2,
    errors: list[str] | None = None,
    raw_meta: dict | None = None,
    duration_ms: int = 42000,
):
    from models import JobScrapeStatus

    status = JobScrapeStatus(status_value)
    started_at = datetime.now(UTC) - timedelta(minutes=started_minutes_ago)
    finished_at = None if status_value == "running" else started_at + timedelta(seconds=42)
    return SimpleNamespace(
        id=100 + started_minutes_ago,
        user_id=1,
        source=source,
        status=status,
        triggered_by="cron",
        started_at=started_at,
        finished_at=finished_at,
        requests_made=10,
        listings_returned=5,
        new_jobs=new_jobs,
        updated_jobs=0,
        errors=errors or [],
        duration_ms=duration_ms,
        raw_meta=raw_meta or {},
        created_at=started_at,
    )


# ── 0.2.5.02 — Submissions dashboard ───────────────────────────────────


def test_submissions_tab_unauth_returns_401(client: TestClient):
    """No session cookie → 401 (parity with /settings/sources)."""
    bare = TestClient(client.app, raise_server_exceptions=True)
    r = bare.get("/settings/submissions")
    assert r.status_code == 401


def test_submissions_tab_empty_renders_inbox_empty_state(client: TestClient, auth_cookies):
    """No failures → inbox empty-state with the empty-state copy."""
    r = client.get("/settings/submissions", cookies=auth_cookies)
    assert r.status_code == 200, r.text
    body = r.text
    assert "data-submission-failures-empty" in body
    assert "No submission failures recorded yet." in body
    # The failures table is NOT in the body when there are no rows.
    assert "data-submission-failures-table" not in body


def test_submissions_tab_populated_renders_aggregate_rows(
    client: TestClient, auth_cookies, _patch_route_helpers
):
    """Multiple (board, kind) rows render with count + latest_at + chip tone."""
    _patch_route_helpers["failures"] = [
        {
            "board": "greenhouse",
            "failure_kind": "captcha",
            "count": 14,
            "latest_at": datetime(2026, 5, 18, 14, 32, tzinfo=UTC),
        },
        {
            "board": "lever",
            "failure_kind": "auth_required",
            "count": 5,
            "latest_at": datetime(2026, 5, 19, 9, 12, tzinfo=UTC),
        },
        {
            "board": "ashby",
            "failure_kind": "rate_limited",
            "count": 2,
            "latest_at": datetime(2026, 5, 20, 1, 2, tzinfo=UTC),
        },
    ]
    r = client.get("/settings/submissions", cookies=auth_cookies)
    assert r.status_code == 200, r.text
    body = r.text
    # Each row's data-* attrs surface the board + kind for the smoke pattern.
    assert 'data-board="greenhouse"' in body
    assert 'data-kind="captcha"' in body
    assert 'data-board="lever"' in body
    assert 'data-kind="auth_required"' in body
    assert 'data-board="ashby"' in body
    assert 'data-kind="rate_limited"' in body
    # Counts surface in the table.
    assert ">14<" in body
    # Chip tone: captcha = amber, auth_required = rose.
    assert "amber-200" in body
    assert "rose-200" in body


def test_submissions_tab_htmx_returns_fragment_not_full_page(client: TestClient, auth_cookies):
    """HX-Request: true → tab body without <html>/<body> chrome."""
    r = client.get(
        "/settings/submissions",
        cookies=auth_cookies,
        headers={"HX-Request": "true"},
    )
    assert r.status_code == 200
    body = r.text
    assert "<html" not in body.lower()
    assert "<body" not in body.lower()
    # Tab body markers still render.
    assert "data-submission-failures-empty" in body


def test_settings_tab_nav_includes_submissions(client: TestClient, auth_cookies):
    """Tab nav strip renders the new SUBMISSIONS tab label."""
    r = client.get("/settings/submissions", cookies=auth_cookies)
    assert r.status_code == 200, r.text
    body = r.text
    # The settings_tabs.html nav renders a link to each tab.
    assert 'href="/settings/submissions"' in body
    assert "Submissions" in body


# ── 0.2.5.03 — LLM cost-cap widget ─────────────────────────────────────


def test_llm_cap_widget_unset_renders_placeholder(
    client: TestClient, auth_cookies, _patch_route_helpers
):
    """Cap unset → placeholder card with .env hint, no progress bar."""
    _patch_route_helpers["settings"] = _make_sources_settings(daily_llm_cost_cap_usd=None)
    _patch_route_helpers["today_cost"] = 1.23
    r = client.get("/settings/llm-provider", cookies=auth_cookies)
    assert r.status_code == 200, r.text
    body = r.text
    assert 'data-llm-cap-state="unset"' in body
    assert "data-llm-cap-placeholder" in body
    assert "DAILY_LLM_COST_CAP_USD" in body
    # No progress element rendered.
    assert "data-llm-cap-progress" not in body
    # Spend amount surfaces in the placeholder copy.
    assert "$1.23" in body


def test_llm_cap_widget_zero_spend_renders_zero_pct_bar(
    client: TestClient, auth_cookies, _patch_route_helpers
):
    """Cap set + zero spend → emerald 0% bar."""
    _patch_route_helpers["settings"] = _make_sources_settings(daily_llm_cost_cap_usd=5.0)
    _patch_route_helpers["today_cost"] = 0.0
    r = client.get("/settings/llm-provider", cookies=auth_cookies)
    assert r.status_code == 200, r.text
    body = r.text
    assert 'data-llm-cap-state="ok"' in body
    assert "data-llm-cap-progress" in body
    # Progress value + max are explicit attributes.
    assert 'value="0.0"' in body
    assert 'max="5.0"' in body
    assert ">0%</span>" in body
    assert "$0.00" in body
    assert "$5.00" in body


def test_llm_cap_widget_partial_spend_renders_correct_pct(
    client: TestClient, auth_cookies, _patch_route_helpers
):
    """Half-spent cap → 50% progress."""
    _patch_route_helpers["settings"] = _make_sources_settings(daily_llm_cost_cap_usd=10.0)
    _patch_route_helpers["today_cost"] = 5.0
    r = client.get("/settings/llm-provider", cookies=auth_cookies)
    assert r.status_code == 200, r.text
    body = r.text
    assert 'data-llm-cap-state="ok"' in body
    assert ">50%</span>" in body


def test_llm_cap_widget_over_cap_renders_rose_warning(
    client: TestClient, auth_cookies, _patch_route_helpers
):
    """Spend ≥ cap → rose progress + Wave 6 throttle note."""
    _patch_route_helpers["settings"] = _make_sources_settings(daily_llm_cost_cap_usd=4.0)
    _patch_route_helpers["today_cost"] = 5.50
    r = client.get("/settings/llm-provider", cookies=auth_cookies)
    assert r.status_code == 200, r.text
    body = r.text
    assert 'data-llm-cap-state="over"' in body
    assert "progress-error" in body
    assert "Cap exceeded" in body
    assert "data-llm-cap-warning" in body


# ── 0.2.5.04 — Scraper-run history table ───────────────────────────────


def test_sources_tab_no_runs_renders_runs_empty_state(
    client: TestClient, auth_cookies, _patch_route_helpers
):
    """Empty recent_scrape_runs → RSS empty-state card."""
    _patch_route_helpers["recent_runs"] = []
    r = client.get("/settings/sources", cookies=auth_cookies)
    assert r.status_code == 200, r.text
    body = r.text
    assert "data-recent-scrape-runs" in body
    assert "data-scrape-runs-empty" in body
    assert "No scraper runs yet" in body
    assert "data-scrape-runs-table" not in body


def test_sources_tab_populated_renders_mixed_status_runs(
    client: TestClient, auth_cookies, _patch_route_helpers
):
    """Mixed-status runs surface status chips + counters + per-source label."""
    from models import JobSource

    runs = [
        _make_run(source=JobSource.LINKEDIN, status_value="success", new_jobs=4),
        _make_run(
            source=JobSource.GREENHOUSE,
            status_value="partial",
            started_minutes_ago=15,
            new_jobs=2,
        ),
        _make_run(
            source=JobSource.LEVER,
            status_value="failed",
            started_minutes_ago=20,
            errors=["lever timed out"],
        ),
        _make_run(
            source=JobSource.ASHBY,
            status_value="timed_out",
            started_minutes_ago=25,
        ),
        _make_run(
            source=JobSource.INDEED,
            status_value="running",
            started_minutes_ago=2,
        ),
    ]
    _patch_route_helpers["recent_runs"] = runs

    r = client.get("/settings/sources", cookies=auth_cookies)
    assert r.status_code == 200, r.text
    body = r.text
    assert "data-scrape-runs-table" in body
    # Each status tone renders.
    assert 'data-scrape-run-status="success"' in body
    assert 'data-scrape-run-status="partial"' in body
    assert 'data-scrape-run-status="failed"' in body
    assert 'data-scrape-run-status="timed_out"' in body
    assert 'data-scrape-run-status="running"' in body
    # Per-source data-source attrs.
    assert 'data-source="linkedin"' in body
    assert 'data-source="greenhouse"' in body
    # Error preview surfaces on failed row.
    assert "lever timed out" in body


def test_sources_tab_caps_recent_runs_at_50_via_service_signature(
    client: TestClient, auth_cookies, monkeypatch
):
    """Plan 54 invariant: helper accepts `limit=50`. Service must enforce."""
    from services import job_service

    captured = {"limit": None}

    async def _spy(session, *, user_id, limit=50):
        captured["limit"] = limit
        return []

    monkeypatch.setattr(job_service, "list_recent_scrape_runs", _spy)

    r = client.get("/settings/sources", cookies=auth_cookies)
    assert r.status_code == 200, r.text
    assert captured["limit"] == 50


def test_sources_tab_does_not_render_raw_meta_or_internal_fields(
    client: TestClient, auth_cookies, _patch_route_helpers
):
    """Defense-in-depth: `raw_meta` JSONB values must NEVER appear in the body.

    The route projects JobScrapeRun → JobScrapeRunRead before rendering, but
    even the projection's `raw_meta` field is intentionally not surfaced in
    the template (see plan § Item 3 rationale — same pattern as PR #146 /
    0.2.0.11c). We pin the invariant here.
    """
    from models import JobSource

    payload = "<script>alert('raw_meta_leak')</script>"
    _patch_route_helpers["recent_runs"] = [
        _make_run(
            source=JobSource.LINKEDIN,
            status_value="success",
            raw_meta={"adapter_used": payload, "rate_limit": {"hits": 7}},
        ),
    ]
    r = client.get("/settings/sources", cookies=auth_cookies)
    assert r.status_code == 200, r.text
    body = r.text
    # Literal payload must NOT appear; nor its HTML-escaped form (we render
    # nothing from raw_meta at all).
    assert "raw_meta_leak" not in body
    assert "adapter_used" not in body


# ── Cross-item smoke ──────────────────────────────────────────────────


def test_submissions_helper_threads_user_id_one_under_phase_1_single_user_mode(
    client: TestClient, auth_cookies, monkeypatch
):
    """The route helper passes user_id=1 to the service (Phase-1 single-user MVP).

    Mirrors the latent IDOR captured against `_build_sources_view` in PR #149
    (`0.2.7.02`). Multi-user enforcement upgrades happen once real auth lands.
    """
    from services import application_service

    captured = {"user_id": None}

    async def _spy(session, *, user_id, since_days=30):
        captured["user_id"] = user_id
        return []

    monkeypatch.setattr(application_service, "aggregate_submission_failures", _spy)
    r = client.get("/settings/submissions", cookies=auth_cookies)
    assert r.status_code == 200
    assert captured["user_id"] == 1


def test_llm_cap_widget_uses_settings_daily_cap_passthrough(
    client: TestClient, auth_cookies, _patch_route_helpers
):
    """Widget reads `cost_cap_usd` straight from the active Settings row."""
    _patch_route_helpers["settings"] = _make_sources_settings(daily_llm_cost_cap_usd=2.50)
    _patch_route_helpers["today_cost"] = 0.25
    r = client.get("/settings/llm-provider", cookies=auth_cookies)
    assert r.status_code == 200, r.text
    body = r.text
    assert "$2.50" in body
    assert "$0.25" in body


# Silence flake8 unused-import on AsyncMock when only a subset of tests need it.
_ = AsyncMock
