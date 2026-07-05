"""HTTP-route tests for `PUT /api/v1/settings/sources`.

Plan 38 / 0.2.0.13 hardening: the route was silently dropping
`scraper_rate_limits` (and the four LinkedIn / Indeed keyword + location
fields). These tests pin the kwarg surface + verify that
`pydantic.ValidationError` from the service layer surfaces as 422 at the
route (not 500).

DB is mocked via `app.dependency_overrides[get_session]` so the test does
not require a live Postgres — same pattern as `tests/test_pages.py`.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

pytestmark = pytest.mark.uses_sample_data_shims


@pytest.fixture(scope="module")
def client() -> TestClient:
    from main import app

    return TestClient(app)


_CSRF = "x" * 48


@pytest.fixture(scope="module")
def auth_cookies() -> dict[str, str]:
    # Plan 58 / 0.2.7.06 — PUT /api/v1/settings/sources is now gated by
    # `require_csrf`; tests must send matching cookie + header.
    return {"naavik_session": "fake-1", "naavik_csrf": _CSRF}


@pytest.fixture(scope="module")
def csrf_headers() -> dict[str, str]:
    return {"X-CSRF-Token": _CSRF}


class _FakeSession:
    """Minimum surface to satisfy `Depends(get_session)` evaluation.

    The route's 422-fast-path triggers when `update_sources` raises
    `ValidationError` (we patch the service for that), so the session
    methods below never actually run in the unit test.
    """

    async def commit(self):  # pragma: no cover
        return None

    async def rollback(self):  # pragma: no cover
        return None

    async def close(self):  # pragma: no cover
        return None


async def _fake_get_session():
    yield _FakeSession()


def test_put_sources_rejects_invalid_scraper_rate_limits_with_422(
    client: TestClient, auth_cookies, csrf_headers, monkeypatch
):
    """`update_sources` raising `ValidationError` → 422 at the route boundary."""
    from db.session import get_session
    from main import app
    from services import settings as settings_service

    async def _raise_validation_error(*args, **kwargs):
        # Surface the same ValidationError the service raises on a bad
        # `scraper_rate_limits` entry (rpm < 0.1 floor).
        raise ValidationError.from_exception_data(
            "RateLimitConfig",
            [
                {
                    "type": "greater_than_equal",
                    "loc": ("rpm",),
                    "input": 0.0,
                    "ctx": {"ge": 0.1},
                },
            ],
        )

    monkeypatch.setattr(settings_service, "update_sources", _raise_validation_error)
    app.dependency_overrides[get_session] = _fake_get_session
    try:
        r = client.put(
            "/api/v1/settings/sources",
            json={
                "scraper_rate_limits": {
                    "linkedin": {"rpm": 0.0, "delay_lo": 1.0, "delay_hi": 3.0},
                },
            },
            cookies=auth_cookies,
            headers=csrf_headers,
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert r.status_code == 422, r.text
    body = r.json()
    assert "scraper_rate_limits" in body.get("detail", "").lower()
    assert "errors" in body
    assert isinstance(body["errors"], list)
    assert len(body["errors"]) >= 1


def test_put_sources_passes_all_kwargs_to_service(
    client: TestClient, auth_cookies, csrf_headers, monkeypatch
):
    """All 8 kwargs (incl. scraper_rate_limits + keyword/location pairs) reach the service."""
    from db.session import get_session
    from main import app
    from services import settings as settings_service

    captured: dict = {}

    async def _capture(session, user_id, **kwargs):
        captured.update(kwargs)
        # Return a SimpleNamespace mirroring the Settings fields the route reads.
        return SimpleNamespace(
            sources_enabled=kwargs.get("sources_enabled") or {},
            source_schedules=kwargs.get("source_schedules") or {},
            workday_companies=kwargs.get("workday_companies") or [],
            linkedin_keywords=kwargs.get("linkedin_keywords") or [],
            linkedin_location=kwargs.get("linkedin_location"),
            indeed_keywords=kwargs.get("indeed_keywords") or [],
            indeed_location=kwargs.get("indeed_location"),
            scraper_rate_limits=kwargs.get("scraper_rate_limits") or {},
        )

    monkeypatch.setattr(settings_service, "update_sources", _capture)
    app.dependency_overrides[get_session] = _fake_get_session
    try:
        payload = {
            "linkedin_keywords": ["staff engineer"],
            "linkedin_location": "Remote",
            "indeed_keywords": ["sre"],
            "indeed_location": "United States",
            "scraper_rate_limits": {
                "linkedin": {"rpm": 1.5, "delay_lo": 2.0, "delay_hi": 4.0},
            },
        }
        r = client.put(
            "/api/v1/settings/sources",
            json=payload,
            cookies=auth_cookies,
            headers=csrf_headers,
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert r.status_code == 200, r.text
    # Service received every payload key — confirms route → service plumbing.
    assert captured["linkedin_keywords"] == ["staff engineer"]
    assert captured["linkedin_location"] == "Remote"
    assert captured["indeed_keywords"] == ["sre"]
    assert captured["indeed_location"] == "United States"
    assert captured["scraper_rate_limits"]["linkedin"]["rpm"] == 1.5
    # Response surfaces every key for GET round-trip parity.
    body = r.json()
    assert body["linkedin_keywords"] == ["staff engineer"]
    assert body["scraper_rate_limits"]["linkedin"]["delay_hi"] == 4.0


# ── Live-DB round-trip (opt-in) ──────────────────────────────────────────

_LIVE = os.environ.get("NAAVIK_LIVE_DB", "").strip().lower() in {"1", "true", "yes"}


@pytest.mark.skipif(
    not _LIVE,
    reason="set NAAVIK_LIVE_DB=1 (and DATABASE_URL) to run live-DB sources round-trip",
)
def test_put_sources_round_trip_persists_all_fields(client: TestClient, auth_cookies, csrf_headers):
    """All 8 update_sources kwargs round-trip through HTTP + live Postgres."""
    payload = {
        "linkedin_keywords": ["staff engineer", "principal"],
        "linkedin_location": "Remote",
        "indeed_keywords": ["sre"],
        "indeed_location": "United States",
        "scraper_rate_limits": {
            "linkedin": {"rpm": 1.5, "delay_lo": 2.0, "delay_hi": 4.0},
        },
    }
    r = client.put(
        "/api/v1/settings/sources", json=payload, cookies=auth_cookies, headers=csrf_headers
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["linkedin_keywords"] == ["staff engineer", "principal"]
    assert body["linkedin_location"] == "Remote"
    assert body["indeed_keywords"] == ["sre"]
    assert body["indeed_location"] == "United States"
    assert body["scraper_rate_limits"]["linkedin"]["rpm"] == 1.5
    assert body["scraper_rate_limits"]["linkedin"]["delay_hi"] == 4.0
