"""`PUT /api/v1/settings/ai-automation` — the consolidated union save (2026-07).

One form submit carries LLM + generation + auto-apply fields; the union
endpoint re-dispatches the (cached) form through the three real handlers.
The `auto_apply_mode` radio (off / dry_run / live) replaces the old stacked
enabled + dry-run toggles.

DB mocked via `app.dependency_overrides[get_session]` — same pattern as
`tests/test_api_settings_generation.py`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.uses_sample_data_shims


@pytest.fixture(scope="module")
def client() -> TestClient:
    from main import app

    return TestClient(app)


_CSRF = "x" * 48


@pytest.fixture(scope="module")
def auth_cookies() -> dict[str, str]:
    return {"naavik_session": "fake-1", "naavik_csrf": _CSRF}


@pytest.fixture(scope="module")
def csrf_headers() -> dict[str, str]:
    return {"X-CSRF-Token": _CSRF}


class _FakeSession:
    async def commit(self):
        return None

    async def rollback(self):
        return None

    async def close(self):
        return None


async def _fake_get_session():
    yield _FakeSession()


@pytest.fixture()
def _stub_db(monkeypatch):
    from db.session import get_session
    from main import app

    app.dependency_overrides[get_session] = _fake_get_session
    yield
    app.dependency_overrides.pop(get_session, None)


def _capture_service_calls(monkeypatch) -> dict:
    """Stub the three settings_service update fns; capture their kwargs."""
    from services import settings as settings_service

    calls: dict[str, dict] = {}

    async def _upd_llm(session, *, user_id, **kw):
        calls["llm"] = kw
        return None

    async def _upd_generation(session, *, user_id, **kw):
        calls["generation"] = kw
        return None

    async def _upd_auto_apply(session, *, user_id, **kw):
        calls["auto_apply"] = kw
        return None

    monkeypatch.setattr(settings_service, "update_llm", _upd_llm)
    monkeypatch.setattr(settings_service, "update_generation", _upd_generation)
    monkeypatch.setattr(settings_service, "update_auto_apply", _upd_auto_apply)
    return calls


@pytest.mark.usefixtures("_stub_db")
def test_union_save_dispatches_all_three_families(
    client: TestClient, auth_cookies, csrf_headers, monkeypatch
):
    calls = _capture_service_calls(monkeypatch)
    r = client.put(
        "/api/v1/settings/ai-automation",
        data={
            "llm_provider": "openai",
            "llm_model": "gpt-5.4-mini",
            "generation_tier": "premium",
            "auto_apply_mode": "live",
            "auto_apply_score_threshold": "0.9",
            "auto_apply_daily_cap": "10",
        },
        cookies=auth_cookies,
        headers=csrf_headers,
    )
    assert r.status_code == 200, r.text
    assert "Saved" in r.text
    assert calls["llm"]["model"] == "gpt-5.4-mini"
    assert calls["generation"]["generation_tier"] == "premium"
    assert calls["auto_apply"]["auto_apply_enabled"] is True
    assert calls["auto_apply"]["auto_apply_dry_run"] is False
    assert calls["auto_apply"]["auto_apply_score_threshold"] == 0.9
    assert calls["auto_apply"]["auto_apply_daily_cap"] == 10


@pytest.mark.usefixtures("_stub_db")
@pytest.mark.parametrize(
    ("mode", "enabled", "dry_run"),
    [("off", False, False), ("dry_run", True, True), ("live", True, False)],
)
def test_auto_apply_mode_radio_maps_to_flags(
    client: TestClient, auth_cookies, csrf_headers, monkeypatch, mode, enabled, dry_run
):
    calls = _capture_service_calls(monkeypatch)
    r = client.put(
        "/api/v1/settings/ai-automation",
        data={"auto_apply_mode": mode, "auto_apply_score_threshold": "0.85"},
        cookies=auth_cookies,
        headers=csrf_headers,
    )
    assert r.status_code == 200, r.text
    assert calls["auto_apply"]["auto_apply_enabled"] is enabled
    assert calls["auto_apply"]["auto_apply_dry_run"] is dry_run


@pytest.mark.usefixtures("_stub_db")
def test_union_save_propagates_first_422(
    client: TestClient, auth_cookies, csrf_headers, monkeypatch
):
    """A field family that fails validation aborts the union save."""
    _capture_service_calls(monkeypatch)
    r = client.put(
        "/api/v1/settings/ai-automation",
        data={"llm_provider": "openai", "api_key": "sk-should-be-env-only"},
        cookies=auth_cookies,
        headers=csrf_headers,
    )
    assert r.status_code == 422
