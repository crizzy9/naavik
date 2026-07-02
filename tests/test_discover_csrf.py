"""Plan 44 (0.2.0.11b) — CSRF gate on `/api/v1/discover` swipe endpoints.

Closes PR #112 hacker MEDIUM finding (Issue #114). The three swipe-mutation
endpoints in `src/ui/routes/discover.py` (`post_skip` / `post_save` /
`post_auto_submit`) gained `Depends(require_csrf)` mirroring the canonical
`post_change_password` pattern at `src/api/auth.py:283-291`.

Each endpoint gets one reject (mismatched cookie + header → 403 + "CSRF" in
body) and one accept (matching cookie + header → status != 403; success or
sample-data 404/200 short-circuits beyond the gate). Auth is bypassed via
`require_authed_session` dependency override so the CSRF dep is exercised
in isolation.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.uses_sample_data_shims

# Tests bcrypt-init: keep cost low (same as test_auth.py).
os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")
# CSRF gate is in-app; the swipe body falls through to `db.sample_data`
# in-memory accessors (plan 60 / 0.2.7.17 removed the dual-mode env var).


@pytest.fixture(autouse=True)
def _restore_sample_data_state():
    """Accept-path tests mutate `APPLICATIONS` + `JOBS` (via `_create_draft`
    + `_set_job_queue_state`). Snapshot + restore so the next test module
    (test_sample_data.py) sees the canonical 14-row APPLICATIONS inventory.
    """
    from db import sample_data as sd

    apps_snap = [a.model_copy(deep=True) for a in sd.APPLICATIONS]
    jobs_snap = [j.model_copy(deep=True) for j in sd.JOBS]
    yield
    sd.APPLICATIONS.clear()
    sd.APPLICATIONS.extend(apps_snap)
    sd.JOBS.clear()
    sd.JOBS.extend(jobs_snap)


def _build_csrf_test_client():
    """Spin up the full FastAPI app with `require_authed_session` overridden
    to return None (fake-session bypass shape). The CSRF dep is the only
    remaining gate; tests assert against its behavior directly.
    """
    from fastapi.testclient import TestClient

    from main import app
    from services.auth import require_authed_session

    async def _bypass_auth():
        return None

    app.dependency_overrides[require_authed_session] = _bypass_auth
    client = TestClient(app, raise_server_exceptions=True)
    return app, client


def _restore(app):
    from services.auth import require_authed_session

    app.dependency_overrides.pop(require_authed_session, None)


# ── post_skip ────────────────────────────────────────────────────────────


def test_discover_skip_rejects_mismatched_csrf() -> None:
    """POST /api/v1/discover/{id}/skip with mismatched cookie/header → 403."""
    app, client = _build_csrf_test_client()
    try:
        r = client.post(
            "/api/v1/discover/1/skip",
            cookies={"naavik_csrf": "cookie-token-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
            headers={"X-CSRF-Token": "header-token-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"},
        )
    finally:
        _restore(app)
    assert r.status_code == 403
    assert "CSRF" in r.text or "csrf" in r.text


def test_discover_skip_accepts_matching_csrf() -> None:
    """POST /api/v1/discover/{id}/skip with matching cookie + header → not 403.

    The gate accepts; the body short-circuits at sample_data with a 200 swipe
    card (sample_data has jobs at low IDs). The point is proving `require_csrf`
    is not the rejection cause on the matching path.
    """
    app, client = _build_csrf_test_client()
    try:
        matching = "matching-token-cccccccccccccccccccccccccccccccccc"
        r = client.post(
            "/api/v1/discover/1/skip",
            cookies={"naavik_csrf": matching},
            headers={"X-CSRF-Token": matching},
        )
    finally:
        _restore(app)
    assert r.status_code != 403


# ── post_save ────────────────────────────────────────────────────────────


def test_discover_save_rejects_mismatched_csrf() -> None:
    """POST /api/v1/discover/{id}/save with mismatched cookie/header → 403."""
    app, client = _build_csrf_test_client()
    try:
        r = client.post(
            "/api/v1/discover/1/save",
            cookies={"naavik_csrf": "cookie-token-ddddddddddddddddddddddddddddddddd"},
            headers={"X-CSRF-Token": "header-token-eeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"},
        )
    finally:
        _restore(app)
    assert r.status_code == 403
    assert "CSRF" in r.text or "csrf" in r.text


def test_discover_save_accepts_matching_csrf() -> None:
    """POST /api/v1/discover/{id}/save with matching cookie + header → not 403."""
    app, client = _build_csrf_test_client()
    try:
        matching = "matching-token-fffffffffffffffffffffffffffffffff"
        r = client.post(
            "/api/v1/discover/1/save",
            cookies={"naavik_csrf": matching},
            headers={"X-CSRF-Token": matching},
        )
    finally:
        _restore(app)
    assert r.status_code != 403


# ── post_auto_submit ─────────────────────────────────────────────────────


def test_discover_auto_submit_rejects_mismatched_csrf() -> None:
    """POST /api/v1/applications/{id}/auto-submit with mismatched cookie/header → 403."""
    app, client = _build_csrf_test_client()
    try:
        r = client.post(
            "/api/v1/applications/1/auto-submit",
            cookies={"naavik_csrf": "cookie-token-ggggggggggggggggggggggggggggggggg"},
            headers={"X-CSRF-Token": "header-token-hhhhhhhhhhhhhhhhhhhhhhhhhhhhhhh"},
        )
    finally:
        _restore(app)
    assert r.status_code == 403
    assert "CSRF" in r.text or "csrf" in r.text


def test_discover_auto_submit_accepts_matching_csrf() -> None:
    """POST /api/v1/applications/{id}/auto-submit with matching cookie + header → not 403."""
    app, client = _build_csrf_test_client()
    try:
        matching = "matching-token-iiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiii"
        r = client.post(
            "/api/v1/applications/1/auto-submit",
            cookies={"naavik_csrf": matching},
            headers={"X-CSRF-Token": matching},
        )
    finally:
        _restore(app)
    assert r.status_code != 403


# ── Plan 56 · item 6 (0.2.7.19) — twin CSRF gaps ─────────────────────────


def test_post_job_by_url_rejects_mismatched_csrf() -> None:
    """POST /api/v1/jobs/by-url with mismatched cookie/header → 403."""
    app, client = _build_csrf_test_client()
    try:
        r = client.post(
            "/api/v1/jobs/by-url",
            json={"url": "https://example.com/jobs/123"},
            cookies={"naavik_csrf": "cookie-token-jjjjjjjjjjjjjjjjjjjjjjjjjjjjjjjjj"},
            headers={"X-CSRF-Token": "header-token-kkkkkkkkkkkkkkkkkkkkkkkkkkkkkkk"},
        )
    finally:
        _restore(app)
    assert r.status_code == 403
    assert "CSRF" in r.text or "csrf" in r.text


def test_post_job_by_url_accepts_matching_csrf(monkeypatch) -> None:
    """POST /api/v1/jobs/by-url with matching cookie + header → not 403.

    The gate accepts; the fetch is stubbed to fail so the body
    short-circuits at the 422 error fragment (no network in tests).
    """
    from scraper.crawl4ai_client import Crawl4AIClient

    async def _fake_fetch(self, url):
        return None

    monkeypatch.setattr(Crawl4AIClient, "fetch_html", _fake_fetch)
    app, client = _build_csrf_test_client()
    try:
        matching = "matching-token-llllllllllllllllllllllllllllllllll"
        r = client.post(
            "/api/v1/jobs/by-url",
            json={"url": "https://example.com/jobs/123"},
            cookies={"naavik_csrf": matching},
            headers={"X-CSRF-Token": matching},
        )
    finally:
        _restore(app)
    assert r.status_code != 403


def test_post_application_manual_rejects_mismatched_csrf() -> None:
    """POST /api/v1/applications/manual with mismatched cookie/header → 403."""
    app, client = _build_csrf_test_client()
    try:
        r = client.post(
            "/api/v1/applications/manual",
            data={"company": "Acme", "role": "Engineer"},
            cookies={"naavik_csrf": "cookie-token-mmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmm"},
            headers={"X-CSRF-Token": "header-token-nnnnnnnnnnnnnnnnnnnnnnnnnnnnnnn"},
        )
    finally:
        _restore(app)
    assert r.status_code == 403
    assert "CSRF" in r.text or "csrf" in r.text


def test_post_application_manual_accepts_matching_csrf() -> None:
    """POST /api/v1/applications/manual with matching cookie + header → not 403.

    Body short-circuits at sample_data with a 204 + HX-Redirect.
    """
    app, client = _build_csrf_test_client()
    try:
        matching = "matching-token-ooooooooooooooooooooooooooooooooo"
        r = client.post(
            "/api/v1/applications/manual",
            data={"company": "Acme", "role": "Engineer"},
            cookies={"naavik_csrf": matching},
            headers={"X-CSRF-Token": matching},
        )
    finally:
        _restore(app)
    assert r.status_code != 403
