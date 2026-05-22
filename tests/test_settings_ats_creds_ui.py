"""Settings · Submissions ATS-credentials panel render (plan 63 / 0.2.7.10 § C.6).

Pins the wire shape of the read-only panel:
- Renders 4 rows (Workday + LinkedIn + Indeed + Generic threshold)
- Configured-vs-not chip flips when env slot toggles
- Tunable threshold row carries the current value
- Phase chips ("Phase 4+" / "Phase 5+") render forward pointers
- Panel is included in the Submissions tab page (NOT a standalone route)
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.uses_sample_data_shims

os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")


@pytest.fixture(scope="module")
def client() -> TestClient:
    from main import app

    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture(scope="module")
def auth_cookies() -> dict[str, str]:
    return {"naavik_session": "fake-1"}


def _make_settings(**overrides):
    base = {
        "user_id": 1,
        "llm_provider": SimpleNamespace(value="anthropic"),
        "llm_model": "claude-3.5-sonnet-20250219",
        "llm_fallback_provider": None,
        "deployment_mode": SimpleNamespace(value="self_hosted"),
        "auto_apply_adapter_confidence_threshold": 0.7,
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
def _patch_route_helpers(monkeypatch):
    from db.session import get_session
    from main import app
    from services import application_service, settings_service

    async def _fake_get_or_create(session, *, user_id):
        return _make_settings()

    async def _fake_failures(session, *, user_id):
        return []

    monkeypatch.setattr(settings_service, "get_or_create", _fake_get_or_create)
    monkeypatch.setattr(application_service, "aggregate_submission_failures", _fake_failures)
    app.dependency_overrides[get_session] = _fake_get_session
    yield
    app.dependency_overrides.pop(get_session, None)


@pytest.fixture
def _clear_ats_env(monkeypatch):
    from config import settings as app_settings

    monkeypatch.setattr(app_settings, "workday_login_token", None)
    monkeypatch.setattr(app_settings, "linkedin_session_cookie", None)
    monkeypatch.setattr(app_settings, "indeed_session_cookie", None)
    monkeypatch.setattr(app_settings, "ats_generic_llm_confidence_threshold", 0.7)


def test_submissions_panel_unauthed_redirects_to_login(client: TestClient):
    """Plan 0.7.0.39: browser top-nav to a gated UI route (no cookie, no
    HX-Request header) → 307 + Location: /login, not a bare 401 JSON page.
    """
    bare = TestClient(client.app, raise_server_exceptions=True)
    r = bare.get("/settings/submissions", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers.get("location") == "/login"


def test_submissions_panel_renders_ats_credentials_section(
    client: TestClient, auth_cookies, _clear_ats_env
):
    r = client.get("/settings/submissions", cookies=auth_cookies)
    assert r.status_code == 200, r.text
    body = r.text
    assert 'data-settings-section="ats-credentials"' in body
    assert "data-ats-credentials-table" in body


def test_ats_panel_renders_one_row_per_board(client: TestClient, auth_cookies, _clear_ats_env):
    r = client.get("/settings/submissions", cookies=auth_cookies)
    body = r.text
    for board_value in ("workday", "linkedin", "indeed", "company_direct"):
        assert f'data-board="{board_value}"' in body


def test_ats_panel_renders_env_var_names(client: TestClient, auth_cookies, _clear_ats_env):
    r = client.get("/settings/submissions", cookies=auth_cookies)
    body = r.text
    assert "WORKDAY_LOGIN_TOKEN" in body
    assert "LINKEDIN_SESSION_COOKIE" in body
    assert "INDEED_SESSION_COOKIE" in body
    assert "ATS_GENERIC_LLM_CONFIDENCE_THRESHOLD" in body


def test_ats_panel_workday_unconfigured_chip(client: TestClient, auth_cookies, _clear_ats_env):
    r = client.get("/settings/submissions", cookies=auth_cookies)
    body = r.text
    # 3 credential rows × "not configured" = 3 chips when nothing is set.
    assert body.count("not configured") == 3


def test_ats_panel_workday_configured_chip_flips_on_env(
    client: TestClient, auth_cookies, monkeypatch, _clear_ats_env
):
    from config import settings as app_settings

    monkeypatch.setattr(app_settings, "workday_login_token", "secret-token")
    r = client.get("/settings/submissions", cookies=auth_cookies)
    body = r.text
    assert "configured" in body  # at least one chip
    # 1 configured + 2 not configured for the credential rows now.
    assert body.count("not configured") == 2


def test_ats_panel_threshold_renders_value(client: TestClient, auth_cookies, _clear_ats_env):
    r = client.get("/settings/submissions", cookies=auth_cookies)
    body = r.text
    # Default 0.7 — formatted to 2 decimals in the partial.
    assert "0.70" in body


def test_ats_panel_phase_chips_render_forward_pointers(
    client: TestClient, auth_cookies, _clear_ats_env
):
    r = client.get("/settings/submissions", cookies=auth_cookies)
    body = r.text
    assert "Phase 4+" in body  # Workday
    assert "Phase 5+" in body  # LinkedIn / Indeed / Generic
