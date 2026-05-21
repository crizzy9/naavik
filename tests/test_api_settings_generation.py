"""HTTP-route tests for `PUT /api/v1/settings/generation`.

Plan 67 round-2 regression guard (PR #168 hacker HIGH-1): a previous
implementation silently wiped `Settings.originality_api_key` on every
Generation-tab form save because the password input never echoes the stored
value (so the browser submits `originality_api_key=""` on every save). The
service no longer treats empty string as a clear; it requires the explicit
`originality_api_key_clear` sentinel.

DB is mocked via `app.dependency_overrides[get_session]` so the test does
not require a live Postgres — same pattern as `tests/test_api_settings_sources.py`.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient


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


def test_put_generation_preserves_api_key_on_empty_form_submit(
    client: TestClient, auth_cookies, csrf_headers, monkeypatch
):
    """The HIGH-1 regression: form re-submit with empty `originality_api_key`
    MUST NOT clobber the stored key. The route drops the empty value before
    calling `update_generation`, so the service never sees `originality_api_key`."""
    from db.session import get_session
    from main import app
    from services import settings_service

    captured: dict = {}

    async def _capture(session, user_id, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            generation_tier=kwargs.get("generation_tier") or "free",
            originality_api_key="sk-existing",
            tier_2_evasion_enabled=bool(kwargs.get("tier_2_evasion_enabled")),
        )

    monkeypatch.setattr(settings_service, "update_generation", _capture)
    app.dependency_overrides[get_session] = _fake_get_session
    try:
        # Simulate the HTMX form save: tier_2 toggled on, password input empty
        r = client.put(
            "/api/v1/settings/generation",
            data={
                "generation_tier": "premium",
                "originality_api_key": "",  # form auto-blanks the password input
                "tier_2_evasion_enabled": "1",
            },
            cookies=auth_cookies,
            headers={**csrf_headers, "Content-Type": "application/x-www-form-urlencoded"},
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert r.status_code == 200, r.text
    # The route MUST pass `originality_api_key=None` (skip) to the service,
    # NOT an empty string. Service-level `None` = preserve.
    assert captured["originality_api_key"] is None
    # Clear sentinel NOT set when value is just empty
    assert captured.get("originality_api_key_clear") is False


def test_put_generation_sets_api_key_when_non_empty(
    client: TestClient, auth_cookies, csrf_headers, monkeypatch
):
    """A non-empty `originality_api_key` payload reaches the service unchanged."""
    from db.session import get_session
    from main import app
    from services import settings_service

    captured: dict = {}

    async def _capture(session, user_id, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            generation_tier="free",
            originality_api_key=kwargs.get("originality_api_key"),
            tier_2_evasion_enabled=False,
        )

    monkeypatch.setattr(settings_service, "update_generation", _capture)
    app.dependency_overrides[get_session] = _fake_get_session
    try:
        r = client.put(
            "/api/v1/settings/generation",
            data={"originality_api_key": "sk-new-key"},
            cookies=auth_cookies,
            headers={**csrf_headers, "Content-Type": "application/x-www-form-urlencoded"},
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert r.status_code == 200, r.text
    assert captured["originality_api_key"] == "sk-new-key"


def test_put_generation_explicit_clear_sentinel_passes_through(
    client: TestClient, auth_cookies, csrf_headers, monkeypatch
):
    """JSON callers that need to clear pass `originality_api_key_clear=true`."""
    from db.session import get_session
    from main import app
    from services import settings_service

    captured: dict = {}

    async def _capture(session, user_id, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            generation_tier="free",
            originality_api_key=None,
            tier_2_evasion_enabled=False,
        )

    monkeypatch.setattr(settings_service, "update_generation", _capture)
    app.dependency_overrides[get_session] = _fake_get_session
    try:
        r = client.put(
            "/api/v1/settings/generation",
            json={"originality_api_key_clear": True},
            cookies=auth_cookies,
            headers=csrf_headers,
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert r.status_code == 200, r.text
    assert captured.get("originality_api_key_clear") is True
