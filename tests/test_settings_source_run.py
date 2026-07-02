"""HTTP-route tests for `POST /_fragments/settings/sources/{source}/run`.

The manual Run-now trigger (Settings · Sources) queues a bounded one-off
scrape via the scheduler. These tests pin the guard ladder:

1. unknown source → 404 chip
2. unconfigured source → 422 chip naming the fix
3. configured source but scheduler not running → 503 chip
4. configured source + running scheduler → 200 "queued" chip + one-off job

DB is mocked via `app.dependency_overrides[get_session]`; the scheduler is
patched at `scheduler.get_scheduler` (imported lazily inside the route).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.uses_sample_data_shims

_CSRF = "x" * 48


@pytest.fixture(scope="module")
def client() -> TestClient:
    from main import app

    return TestClient(app)


@pytest.fixture(scope="module")
def auth_cookies() -> dict[str, str]:
    return {"naavik_session": "fake-1", "naavik_csrf": _CSRF}


@pytest.fixture(scope="module")
def csrf_headers() -> dict[str, str]:
    return {"X-CSRF-Token": _CSRF}


@pytest.fixture
def _settings_stub(monkeypatch):
    """Route reads Settings via settings_service.get_or_create."""
    from services import settings_service

    holder = SimpleNamespace(
        linkedin_keywords=[],
        indeed_keywords=[],
        workday_companies=[],
    )

    async def _get_or_create(_session, *, user_id):
        return holder

    monkeypatch.setattr(settings_service, "get_or_create", _get_or_create)
    return holder


def test_run_unknown_source_404(client, auth_cookies, csrf_headers, _settings_stub):
    r = client.post(
        "/_fragments/settings/sources/nonsense/run",
        cookies=auth_cookies,
        headers=csrf_headers,
    )
    assert r.status_code == 404
    assert "unknown source" in r.text


def test_run_unconfigured_source_422(client, auth_cookies, csrf_headers, _settings_stub):
    r = client.post(
        "/_fragments/settings/sources/linkedin/run",
        cookies=auth_cookies,
        headers=csrf_headers,
    )
    assert r.status_code == 422
    assert "not configured" in r.text
    assert "target titles" in r.text


def test_run_configured_but_scheduler_down_503(
    client, auth_cookies, csrf_headers, _settings_stub, monkeypatch
):
    import scheduler as scheduler_pkg

    _settings_stub.linkedin_keywords = ["swe"]
    monkeypatch.setattr(scheduler_pkg, "get_scheduler", lambda: None)
    r = client.post(
        "/_fragments/settings/sources/linkedin/run",
        cookies=auth_cookies,
        headers=csrf_headers,
    )
    assert r.status_code == 503
    assert "scheduler not running" in r.text


def test_run_configured_queues_one_off(
    client, auth_cookies, csrf_headers, _settings_stub, monkeypatch
):
    import scheduler as scheduler_pkg

    _settings_stub.linkedin_keywords = ["swe"]
    added: list[dict] = []

    class _FakeScheduler:
        def get_job(self, job_id):
            assert job_id == "scraping.linkedin"
            return SimpleNamespace(func=lambda: None, id=job_id)

        def add_job(self, func, trigger, **kw):
            added.append(kw)

    monkeypatch.setattr(scheduler_pkg, "get_scheduler", lambda: _FakeScheduler())
    r = client.post(
        "/_fragments/settings/sources/linkedin/run",
        cookies=auth_cookies,
        headers=csrf_headers,
    )
    assert r.status_code == 200
    assert "queued" in r.text
    assert len(added) == 1
    assert added[0]["kwargs"]["max_listings"] == 10
    assert added[0]["kwargs"]["only_user_id"] == 1
    assert added[0]["id"].startswith("scraping.linkedin-manual-")


def test_run_requires_csrf(client, auth_cookies, _settings_stub):
    r = client.post(
        "/_fragments/settings/sources/linkedin/run",
        cookies=auth_cookies,
    )
    assert r.status_code == 403
