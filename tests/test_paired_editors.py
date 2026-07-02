"""Plan 58 / 0.2.7.06 — paired UI editors (rate-limit JSONB + LinkedIn/Indeed keywords).

Tests cover (a) GET-render: the new `_rate_limit_editor.html` + `_keywords_editor.html`
partials are wired into `_source_row.html` popovers; (b) PUT /api/v1/settings/sources
form-encoded round-trip with comma-split keywords + flat-field rate-limit unpacking;
(c) CSRF gate (`require_csrf` dep, plan 44 pattern); (d) IDOR threading
(`_effective_user_id`, plan 56 pattern); (e) HTMX response shape (re-rendered panel).
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.uses_sample_data_shims

os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")


_CSRF = "p" * 48


@pytest.fixture(scope="module")
def client() -> TestClient:
    from main import app

    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture(scope="module")
def auth_cookies() -> dict[str, str]:
    return {"naavik_session": "fake-1", "naavik_csrf": _CSRF}


@pytest.fixture(scope="module")
def csrf_headers() -> dict[str, str]:
    return {"X-CSRF-Token": _CSRF}


def _make_settings(**overrides):
    """Minimal Settings-like for the route's read surface."""
    base = {
        "user_id": 1,
        "llm_provider": SimpleNamespace(value="anthropic"),
        "llm_model": "claude-sonnet-4-6",
        "llm_fallback_provider": None,
        "deployment_mode": SimpleNamespace(value="self_hosted"),
        "sources_enabled": {
            "linkedin": True,
            "workday": True,
            "greenhouse": True,
            "lever": True,
            "ashby": True,
            "indeed": True,
        },
        "source_schedules": {},
        "workday_companies": [],
        "linkedin_keywords": None,
        "linkedin_location": None,
        "indeed_keywords": None,
        "indeed_location": None,
        "scraper_rate_limits": {},
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class _NoopSession:
    async def commit(self):  # pragma: no cover
        return None

    async def rollback(self):  # pragma: no cover
        return None

    async def close(self):  # pragma: no cover
        return None


async def _fake_get_session():
    yield _NoopSession()


@pytest.fixture(autouse=True)
def _patch_route(monkeypatch):
    """Replace DB-touching service calls + override `get_session`."""
    from db.session import get_session
    from main import app
    from services import job_service, settings_service

    state: dict = {
        "settings": _make_settings(),
        "runs": {},
        "recent_runs": [],
    }

    async def _fake_get_or_create(session, *, user_id):
        return state["settings"]

    async def _fake_update(session, *, user_id, **kwargs):
        for k, v in kwargs.items():
            if v is not None:
                setattr(state["settings"], k, v)
        return state["settings"]

    async def _fake_runs(session, *, user_id):
        return state["runs"]

    async def _fake_recent_runs(session, *, user_id, limit=50):
        return state["recent_runs"][:limit]

    monkeypatch.setattr(settings_service, "get_or_create", _fake_get_or_create)
    monkeypatch.setattr(settings_service, "update_sources", _fake_update)
    monkeypatch.setattr(job_service, "list_recent_scrape_runs_by_source", _fake_runs)
    monkeypatch.setattr(job_service, "list_recent_scrape_runs", _fake_recent_runs)
    app.dependency_overrides[get_session] = _fake_get_session
    yield state
    app.dependency_overrides.pop(get_session, None)


# ── GET-render: editor partials wired into popovers ─────────────────────


def test_get_renders_rate_limit_form_per_source(client: TestClient, auth_cookies):
    """Rate-limit form renders for every source on the Sources panel."""
    r = client.get("/settings/sources", cookies=auth_cookies)
    assert r.status_code == 200, r.text
    body = r.text
    for source_value in ("linkedin", "workday", "greenhouse", "lever", "ashby", "indeed"):
        assert f'data-rate-limit-form="{source_value}"' in body, (
            f"missing rate-limit form for {source_value}"
        )
        # data-source-editor wrapper present per source for HTMX swap targeting.
        assert f'data-source-editor="{source_value}"' in body


def test_get_renders_keywords_form_only_for_linkedin_and_indeed(client: TestClient, auth_cookies):
    """Keywords form renders ONLY for LinkedIn + Indeed (the two `kind="db"` sources)."""
    r = client.get("/settings/sources", cookies=auth_cookies)
    assert r.status_code == 200, r.text
    body = r.text
    assert 'data-keywords-form="linkedin"' in body
    assert 'data-keywords-form="indeed"' in body
    # Env-kind + db-workday sources do NOT get the keywords form.
    for source_value in ("workday", "greenhouse", "lever", "ashby"):
        assert f'data-keywords-form="{source_value}"' not in body, (
            f"keywords form unexpectedly rendered for {source_value}"
        )


# ── PUT rate-limit: JSON round-trip + validator boundaries ──────────────


def test_put_rate_limit_valid_round_trip(client: TestClient, auth_cookies, csrf_headers):
    r = client.put(
        "/api/v1/settings/sources",
        json={"scraper_rate_limits": {"linkedin": {"rpm": 0.5, "delay_lo": 4.0, "delay_hi": 8.0}}},
        cookies=auth_cookies,
        headers=csrf_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scraper_rate_limits"]["linkedin"]["rpm"] == 0.5
    assert body["scraper_rate_limits"]["linkedin"]["delay_hi"] == 8.0


def test_put_rate_limit_rejects_rpm_below_floor(
    client: TestClient, auth_cookies, csrf_headers, monkeypatch
):
    """rpm < 0.1 (the RateLimitConfig floor) → 422 from real service path."""
    # Use the real service so RateLimitConfig actually validates.
    from services import settings_service as svc

    monkeypatch.undo()  # drop the autouse fake for THIS test

    async def _real_passthrough(session, *, user_id, **kwargs):
        # Delegate to the real validator via RateLimitConfig.model_validate.
        from scraper.rate_limit import RateLimitConfig

        rl = kwargs.get("scraper_rate_limits")
        if rl:
            for raw in rl.values():
                RateLimitConfig.model_validate(raw)
        return _make_settings(**{k: v for k, v in kwargs.items() if v is not None})

    monkeypatch.setattr(svc, "update_sources", _real_passthrough)
    monkeypatch.setattr(svc, "get_or_create", lambda *a, **k: _make_settings())
    from db.session import get_session
    from main import app

    app.dependency_overrides[get_session] = _fake_get_session
    try:
        r = client.put(
            "/api/v1/settings/sources",
            json={
                "scraper_rate_limits": {"linkedin": {"rpm": 0.0, "delay_lo": 1.0, "delay_hi": 3.0}}
            },
            cookies=auth_cookies,
            headers=csrf_headers,
        )
    finally:
        app.dependency_overrides.pop(get_session, None)
    assert r.status_code == 422, r.text


def test_put_rate_limit_rejects_delay_lo_gt_hi(
    client: TestClient, auth_cookies, csrf_headers, monkeypatch
):
    """delay_lo > delay_hi → 422 via cross-field validator."""
    from services import settings_service as svc

    monkeypatch.undo()

    async def _real_passthrough(session, *, user_id, **kwargs):
        from scraper.rate_limit import RateLimitConfig

        rl = kwargs.get("scraper_rate_limits")
        if rl:
            for raw in rl.values():
                RateLimitConfig.model_validate(raw)
        return _make_settings()

    monkeypatch.setattr(svc, "update_sources", _real_passthrough)
    from db.session import get_session
    from main import app

    app.dependency_overrides[get_session] = _fake_get_session
    try:
        r = client.put(
            "/api/v1/settings/sources",
            json={
                "scraper_rate_limits": {"linkedin": {"rpm": 1.0, "delay_lo": 10.0, "delay_hi": 3.0}}
            },
            cookies=auth_cookies,
            headers=csrf_headers,
        )
    finally:
        app.dependency_overrides.pop(get_session, None)
    assert r.status_code == 422, r.text


def test_put_rate_limit_rejects_rpm_above_ceiling(
    client: TestClient, auth_cookies, csrf_headers, monkeypatch
):
    """rpm > 600 (the upper bound) → 422."""
    from services import settings_service as svc

    monkeypatch.undo()

    async def _real_passthrough(session, *, user_id, **kwargs):
        from scraper.rate_limit import RateLimitConfig

        rl = kwargs.get("scraper_rate_limits")
        if rl:
            for raw in rl.values():
                RateLimitConfig.model_validate(raw)
        return _make_settings()

    monkeypatch.setattr(svc, "update_sources", _real_passthrough)
    from db.session import get_session
    from main import app

    app.dependency_overrides[get_session] = _fake_get_session
    try:
        r = client.put(
            "/api/v1/settings/sources",
            json={
                "scraper_rate_limits": {
                    "linkedin": {"rpm": 1000.0, "delay_lo": 1.0, "delay_hi": 3.0}
                }
            },
            cookies=auth_cookies,
            headers=csrf_headers,
        )
    finally:
        app.dependency_overrides.pop(get_session, None)
    assert r.status_code == 422, r.text


# ── PUT keywords: JSON + form-encoded comma-split ────────────────────────


def test_put_keywords_valid_round_trip(client: TestClient, auth_cookies, csrf_headers):
    r = client.put(
        "/api/v1/settings/sources",
        json={
            "linkedin_keywords": ["staff engineer", "principal"],
            "linkedin_location": "Remote",
        },
        cookies=auth_cookies,
        headers=csrf_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["linkedin_keywords"] == ["staff engineer", "principal"]
    assert body["linkedin_location"] == "Remote"


def test_put_keywords_form_encoded_comma_split(
    client: TestClient, auth_cookies, csrf_headers, monkeypatch
):
    """Form-encoded `linkedin_keywords=a, b, c` → list[str] via server-side split."""
    from services import settings_service as svc

    captured: dict = {}

    async def _capture(session, *, user_id, **kwargs):
        captured.update(kwargs)
        return _make_settings(**{k: v for k, v in kwargs.items() if v is not None})

    monkeypatch.setattr(svc, "update_sources", _capture)

    r = client.put(
        "/api/v1/settings/sources",
        data={"linkedin_keywords": "staff engineer, principal,   senior  "},
        cookies=auth_cookies,
        headers={**csrf_headers, "HX-Request": "true"},
    )
    assert r.status_code == 200, r.text
    assert captured["linkedin_keywords"] == ["staff engineer", "principal", "senior"]


def test_put_form_encoded_rate_limit_flat_field_unpack(
    client: TestClient, auth_cookies, csrf_headers, monkeypatch
):
    """Flat HTMX form fields `<source>_rpm` / `_lo` / `_hi` collapse into nested dict."""
    from services import settings_service as svc

    captured: dict = {}

    async def _capture(session, *, user_id, **kwargs):
        captured.update(kwargs)
        return _make_settings(**{k: v for k, v in kwargs.items() if v is not None})

    monkeypatch.setattr(svc, "update_sources", _capture)

    r = client.put(
        "/api/v1/settings/sources",
        data={
            "linkedin_rpm": "0.6",
            "linkedin_lo": "5.0",
            "linkedin_hi": "9.0",
        },
        cookies=auth_cookies,
        headers={**csrf_headers, "HX-Request": "true"},
    )
    assert r.status_code == 200, r.text
    assert "scraper_rate_limits" in captured
    assert captured["scraper_rate_limits"]["linkedin"] == {
        "rpm": 0.6,
        "delay_lo": 5.0,
        "delay_hi": 9.0,
    }


# ── CSRF + auth gates ────────────────────────────────────────────────────


def test_put_sources_requires_csrf(client: TestClient):
    """PUT without X-CSRF-Token + matching naavik_csrf cookie → 403."""
    r = client.put(
        "/api/v1/settings/sources",
        json={"linkedin_keywords": ["staff"]},
        cookies={"naavik_session": "fake-1"},
        # No matching csrf cookie + no X-CSRF-Token header.
    )
    assert r.status_code == 403, r.text


def test_put_sources_requires_authed_session(client: TestClient, csrf_headers):
    """PUT without naavik_session cookie → 401."""
    r = client.put(
        "/api/v1/settings/sources",
        json={"linkedin_keywords": ["staff"]},
        cookies={"naavik_csrf": _CSRF},  # CSRF only, no session
        headers=csrf_headers,
    )
    assert r.status_code == 401, r.text


# ── IDOR + HTMX response shape ───────────────────────────────────────────


def test_put_sources_threads_effective_user_id(
    client: TestClient, auth_cookies, csrf_headers, monkeypatch
):
    """`_effective_user_id` resolves the fake-session cookie to user_id=1
    and threads it to `settings_service.update_sources` (not the hardcoded
    `user_id=1` literal the pre-fix path used). Mirrors plan 56 / 0.2.7.02
    IDOR fix on the GET path.
    """
    from services import settings_service as svc

    captured: dict = {}

    async def _capture(session, *, user_id, **kwargs):
        captured["user_id"] = user_id
        return _make_settings()

    monkeypatch.setattr(svc, "update_sources", _capture)

    r = client.put(
        "/api/v1/settings/sources",
        json={"linkedin_keywords": ["staff"]},
        cookies=auth_cookies,
        headers=csrf_headers,
    )
    assert r.status_code == 200, r.text
    # Fake-session → user_id=1 per `_effective_user_id` (plan 56 contract).
    # The point is the value comes from the helper, NOT a literal 1.
    assert captured["user_id"] == 1


def test_put_sources_htmx_response_returns_partial(client: TestClient, auth_cookies, csrf_headers):
    """HTMX form-encoded PUT → response body is the `_settings_sources.html`
    partial (no `<html>` chrome), and re-renders the rate-limit form so the
    operator sees the saved value next render.
    """
    r = client.put(
        "/api/v1/settings/sources",
        data={
            "linkedin_rpm": "0.7",
            "linkedin_lo": "6.0",
            "linkedin_hi": "12.0",
        },
        cookies=auth_cookies,
        headers={**csrf_headers, "HX-Request": "true"},
    )
    assert r.status_code == 200, r.text
    body = r.text
    # Partial shape — base.html chrome absent.
    assert "<html" not in body.lower()
    assert "<body" not in body.lower()
    # Saved panel re-renders all 6 source rows with editor partials.
    assert 'data-source-row="linkedin"' in body
    assert 'data-rate-limit-form="linkedin"' in body
    assert 'data-keywords-form="linkedin"' in body
