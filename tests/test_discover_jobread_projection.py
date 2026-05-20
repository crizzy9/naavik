"""Plan 57 / 0.2.7.01 — `JobRead` projection on discover.py callsites.

Filed via PR #146 hacker review (NOTE-1). Five callsites in
`src/ui/routes/discover.py` previously returned `Job.model_dump(mode="json")`
directly — once discover graduates from sample-data to live
`job_service.list_jobs`, that path would leak scraper-controlled `raw_meta`
JSONB through the public API. `JobRead` (at `src/models/job.py:248-294`)
intentionally omits `raw_meta`; this test pins the projection across all
five callsites so any future regression surfaces immediately.

Pattern mirrors `tests/test_stub_endpoints.py::test_jobs_get_by_id` (plan 46
/ 0.2.0.11c — the same projection on `/api/v1/jobs/{id}`).
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")
os.environ.setdefault("NAAVIK_DEBUG", "1")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from main import app
    from services.auth import require_authed_session

    async def _bypass_auth():
        return None

    app.dependency_overrides[require_authed_session] = _bypass_auth
    yield TestClient(app, raise_server_exceptions=True)
    app.dependency_overrides.pop(require_authed_session, None)


_CSRF_TOKEN = "matching-token-projection-aaaaaaaaaaaaaaaaaaaaa"
_CSRF_HEADERS = {"X-CSRF-Token": _CSRF_TOKEN}
_CSRF_COOKIES = {"naavik_csrf": _CSRF_TOKEN}


def _assert_no_raw_meta_and_has_id(item: dict) -> None:
    assert "raw_meta" not in item, f"raw_meta leaked through JobRead projection: {item!r}"
    assert "id" in item, "JobRead.id missing — projection collapsed unexpectedly"
    assert "external_id" in item, "JobRead.external_id missing — projection collapsed unexpectedly"


# ── GET /api/v1/jobs (get_jobs) ──────────────────────────────────────────


def test_get_jobs_list_uses_jobread_projection(client):
    r = client.get("/api/v1/jobs")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert len(body["items"]) > 0
    for item in body["items"]:
        _assert_no_raw_meta_and_has_id(item)


# ── POST /api/v1/jobs/by-url (post_job_by_url) ───────────────────────────


def test_post_job_by_url_uses_jobread_projection(client):
    r = client.post(
        "/api/v1/jobs/by-url",
        json={"url": "https://example.com/jobs/projection-test"},
        cookies=_CSRF_COOKIES,
        headers=_CSRF_HEADERS,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    _assert_no_raw_meta_and_has_id(body)


# ── POST /api/v1/jobs/{id}/rescore (post_rescore) ────────────────────────


def test_post_rescore_uses_jobread_projection(client):
    # Pull any sample-data job_id off the list endpoint first; sample-data
    # IDs aren't 1-anchored (USER.id=1 but Job IDs start higher).
    listing = client.get("/api/v1/jobs").json()
    job_id = listing["items"][0]["id"]
    r = client.post(f"/api/v1/jobs/{job_id}/rescore")
    assert r.status_code == 200, r.text
    body = r.json()
    _assert_no_raw_meta_and_has_id(body)


# ── GET /api/v1/discover/saved (discover_saved) ──────────────────────────


def test_get_discover_saved_uses_jobread_projection(client):
    r = client.get("/api/v1/discover/saved")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    for item in body:
        _assert_no_raw_meta_and_has_id(item)


# ── GET /api/v1/discover/skipped (discover_skipped) ──────────────────────


def test_get_discover_skipped_uses_jobread_projection(client):
    r = client.get("/api/v1/discover/skipped")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    for item in body:
        _assert_no_raw_meta_and_has_id(item)
