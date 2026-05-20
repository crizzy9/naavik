"""Settings · Sources sub-tab route tests — plan 49 / 0.2.0.16.

Covers the per-row contract in plan § D.1 + the 8-test slate in plan § F:
unauth 401, no-runs renders never-run, mixed runs render latest-per-source,
configured-vs-unconfigured indicator branch on env + DB inputs, XSS
regression for `raw_meta` + scraper-controlled `errors`, HTMX fragment
shape, resolved rate-limit rendering, RUNNING-state chip.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")
os.environ["NAAVIK_PERSISTENCE"] = "memory"


@pytest.fixture(scope="module")
def client() -> TestClient:
    from main import app

    c = TestClient(app, raise_server_exceptions=True)
    return c


@pytest.fixture(scope="module")
def auth_cookies() -> dict[str, str]:
    return {"naavik_session": "fake-1"}


def _make_settings(**overrides):
    """Build a minimal Settings-like object matching the route's read surface."""
    base = {
        "user_id": 1,
        "llm_provider": SimpleNamespace(value="anthropic"),
        "llm_model": "claude-3.5-sonnet-20250219",
        "llm_fallback_provider": None,
        "deployment_mode": SimpleNamespace(value="self_hosted"),
        "sources_enabled": {
            "linkedin": True,
            "workday": True,
            "greenhouse": True,
            "lever": True,
            "ashby": True,
            "indeed": False,
        },
        "source_schedules": {
            "linkedin": "*/30 * * * *",
            "workday": "0 * * * *",
            "greenhouse": "0 * * * *",
        },
        "workday_companies": [],
        "linkedin_keywords": None,
        "linkedin_location": None,
        "indeed_keywords": None,
        "indeed_location": None,
        "scraper_rate_limits": {},
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _make_run(
    *, source, status_value: str, started_minutes_ago: int = 30, raw_meta=None, errors=None
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
        new_jobs=2,
        updated_jobs=0,
        errors=errors or [],
        duration_ms=42000,
        raw_meta=raw_meta or {},
        created_at=started_at,
    )


class _NoopSession:
    """Minimum surface for `Depends(get_session)` — real DB ops are
    monkeypatched at the service layer so this never actually runs SQL.
    """

    async def commit(self):  # pragma: no cover
        return None

    async def rollback(self):  # pragma: no cover
        return None

    async def close(self):  # pragma: no cover
        return None


async def _fake_get_session():
    yield _NoopSession()


@pytest.fixture(autouse=True)
def _patch_route_helpers(monkeypatch):
    """Replace `settings_service.get_or_create` + `list_recent_scrape_runs_by_source`
    with controllable in-memory fakes for each test + override `get_session`.

    Default state: a Settings row with empty keyword/company lists, no scrape
    runs. Tests override per-case by writing into the returned `state` dict.
    """
    from db.session import get_session
    from main import app
    from services import job_service, settings_service

    state: dict = {
        "settings": _make_settings(),
        "runs": {},
    }

    async def _fake_get_or_create(session, *, user_id):
        return state["settings"]

    async def _fake_runs(session, *, user_id):
        return state["runs"]

    monkeypatch.setattr(settings_service, "get_or_create", _fake_get_or_create)
    monkeypatch.setattr(job_service, "list_recent_scrape_runs_by_source", _fake_runs)
    app.dependency_overrides[get_session] = _fake_get_session
    yield state
    app.dependency_overrides.pop(get_session, None)


def test_get_unauth_returns_401(client: TestClient):
    """`/settings/sources` without session cookie → 401."""
    bare = TestClient(client.app, raise_server_exceptions=True)
    r = bare.get("/settings/sources")
    assert r.status_code == 401


def test_get_authed_no_runs_renders_never_run(client: TestClient, auth_cookies):
    """No JobScrapeRun rows → every row shows `never run`."""
    r = client.get("/settings/sources", cookies=auth_cookies)
    assert r.status_code == 200, r.text
    body = r.text
    # 6 source rows render; each gets a never-run marker because runs={}.
    for source_value in ("linkedin", "workday", "greenhouse", "lever", "ashby", "indeed"):
        assert f'data-source-row="{source_value}"' in body
    assert body.count('data-source-last-run="never"') == 6
    assert "never run" in body


def test_get_authed_mixed_runs_renders_latest_per_source(
    client: TestClient, auth_cookies, _patch_route_helpers
):
    """Sources with runs render status chip + timestamp; sources without remain never-run."""
    from models import JobSource

    _patch_route_helpers["runs"] = {
        JobSource.LINKEDIN: _make_run(source=JobSource.LINKEDIN, status_value="success"),
        JobSource.GREENHOUSE: _make_run(
            source=JobSource.GREENHOUSE, status_value="partial", started_minutes_ago=120
        ),
    }

    r = client.get("/settings/sources", cookies=auth_cookies)
    assert r.status_code == 200, r.text
    body = r.text
    assert 'data-source-status="success"' in body
    assert 'data-source-status="partial"' in body
    # Indeed (no run) still shows never-run.
    assert 'data-source-row="indeed"' in body
    # Workday + Lever + Ashby also never-run since their runs aren't seeded.
    assert body.count('data-source-last-run="never"') >= 4


def test_get_renders_configured_indicator_per_source(
    client: TestClient, auth_cookies, monkeypatch, _patch_route_helpers
):
    """Configured chip toggles based on env-vs-DB composition (plan § D.3)."""
    from config import settings as app_settings

    monkeypatch.setattr(app_settings, "greenhouse_companies", ["scale"])
    monkeypatch.setattr(app_settings, "lever_companies", None)
    monkeypatch.setattr(app_settings, "ashby_companies", None)

    _patch_route_helpers["settings"] = _make_settings(
        workday_companies=[],
        linkedin_keywords=["python"],
        indeed_keywords=None,
    )

    r = client.get("/settings/sources", cookies=auth_cookies)
    assert r.status_code == 200, r.text
    body = r.text
    # Configured chips appear for the sources with config.
    assert body.count('data-source-configured="true"') == 2
    # Not-configured for the rest.
    assert body.count('data-source-configured="false"') == 4


def test_get_xss_payload_in_raw_meta_escaped(
    client: TestClient, auth_cookies, _patch_route_helpers
):
    """`<script>` in raw_meta + `errors` round-trips as HTML-escaped text.

    OQ.4 locked YES on covering scraper-controlled `errors` too. The Sources
    panel doesn't render `raw_meta` / `errors` directly (last-run UI only
    surfaces status + timestamp), so the panel is safe by composition; this
    test pins the invariant that no template path leaks the payload.
    """
    from models import JobSource

    payload = "<script>alert(1)</script>"
    img_payload = "<img src=x onerror=alert(1)>"
    _patch_route_helpers["runs"] = {
        JobSource.LINKEDIN: _make_run(
            source=JobSource.LINKEDIN,
            status_value="success",
            raw_meta={"user_agent": payload},
            errors=[img_payload],
        ),
    }

    r = client.get("/settings/sources", cookies=auth_cookies)
    assert r.status_code == 200
    body = r.text
    # Literal payload must NOT appear; only escaped form is acceptable.
    assert "<script>alert(1)</script>" not in body
    assert "<img src=x onerror=alert(1)>" not in body


def test_htmx_swap_returns_partial_not_full_page(client: TestClient, auth_cookies):
    """HX-Request: true → fragment without base layout chrome."""
    r = client.get(
        "/settings/sources",
        cookies=auth_cookies,
        headers={"HX-Request": "true"},
    )
    assert r.status_code == 200
    body = r.text
    # Page chrome absent — fragment shape.
    assert "<html" not in body.lower()
    assert "<body" not in body.lower()
    # Panel content still renders.
    assert 'data-source-row="linkedin"' in body


def test_resolved_rate_limit_rendered_per_source(
    client: TestClient, auth_cookies, _patch_route_helpers
):
    """Operator override surfaces on the matching row; others fall back to class-attr defaults."""
    _patch_route_helpers["settings"] = _make_settings(
        scraper_rate_limits={
            "linkedin": {"rpm": 0.5, "delay_lo": 4.0, "delay_hi": 8.0},
        },
    )

    r = client.get("/settings/sources", cookies=auth_cookies)
    assert r.status_code == 200, r.text
    body = r.text
    # Operator override (0.5 rpm + 4.0–8.0s) shows on LinkedIn.
    assert "0.50 rpm" in body
    assert "4.0&#8211;8.0s" in body or "4.0–8.0s" in body
    # Greenhouse fallback (20 rpm) still renders for the other rows.
    assert "20.00 rpm" in body


def test_running_status_renders_running_chip(
    client: TestClient, auth_cookies, _patch_route_helpers
):
    """`status=RUNNING` (no finished_at) renders the running chip, not a timestamp."""
    from models import JobSource

    _patch_route_helpers["runs"] = {
        JobSource.LINKEDIN: _make_run(
            source=JobSource.LINKEDIN, status_value="running", started_minutes_ago=8
        ),
    }

    r = client.get("/settings/sources", cookies=auth_cookies)
    assert r.status_code == 200, r.text
    body = r.text
    assert 'data-source-status="running"' in body
    assert "running…" in body
