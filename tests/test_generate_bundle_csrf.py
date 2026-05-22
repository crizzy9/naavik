"""CSRF guard on POST /api/v1/applications/{id}/generate-bundle — plan 66 round-2 delta.

Hacker MED-1: state-mutating endpoint was missing the double-submit guard.
Matches pattern from put_status + scheduler /run / /pause / /resume.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.uses_sample_data_shims

# bcrypt cost low for test isolation (mirrors test_scheduler_endpoints.py).
os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")


_MATCHING = "matching-csrf-token-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def _build_client():
    """Spin up the FastAPI app w/ auth + session bypass."""
    from fastapi.testclient import TestClient

    from db.session import get_session
    from main import app
    from services.auth import require_password_complete

    fake_user = SimpleNamespace(id=1, email="test@x.y", must_change_password=False)

    async def _bypass_auth():
        return fake_user

    async def _stub_session():
        # CSRF tests don't exercise the DB layer — the handler 404s on the
        # missing application before any DB call is needed. Yield None and
        # rely on the route to short-circuit on get_application returning None.
        class _Stub:
            async def exec(self, *a, **kw):
                class _R:
                    def one_or_none(self):
                        return None

                    def all(self):
                        return []

                return _R()

            async def commit(self):
                return None

            async def flush(self):
                return None

            def add(self, *a, **kw):
                return None

        yield _Stub()

    app.dependency_overrides[require_password_complete] = _bypass_auth
    app.dependency_overrides[get_session] = _stub_session
    client = TestClient(app, raise_server_exceptions=True)
    return app, client


def _restore(app):
    from db.session import get_session
    from services.auth import require_password_complete

    app.dependency_overrides.pop(require_password_complete, None)
    app.dependency_overrides.pop(get_session, None)


def test_generate_bundle_no_csrf_returns_403():
    """POST /generate-bundle without matching CSRF cookie+header → 403."""
    app, client = _build_client()
    try:
        r = client.post(
            "/api/v1/applications/42/generate-bundle",
            json={},
            cookies={"naavik_csrf": "cookie-token-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"},
            headers={"X-CSRF-Token": "header-token-cccccccccccccccccccccccccccccc"},
        )
    finally:
        _restore(app)
    assert r.status_code == 403
    assert "CSRF" in r.text or "csrf" in r.text


def test_generate_bundle_missing_csrf_cookie_returns_403():
    """POST /generate-bundle with only X-CSRF-Token header (no cookie) → 403."""
    app, client = _build_client()
    try:
        r = client.post(
            "/api/v1/applications/42/generate-bundle",
            json={},
            headers={"X-CSRF-Token": _MATCHING},
        )
    finally:
        _restore(app)
    assert r.status_code == 403


def test_generate_bundle_with_matching_csrf_passes_to_handler():
    """Matching cookie+header passes CSRF; handler then 404s on missing app (expected)."""
    app, client = _build_client()
    try:
        r = client.post(
            "/api/v1/applications/99999/generate-bundle",
            json={},
            cookies={"naavik_csrf": _MATCHING},
            headers={"X-CSRF-Token": _MATCHING},
        )
    finally:
        _restore(app)
    # Past CSRF gate; falls through to handler which returns 404 (or 500/422)
    # — what matters: NOT 403. Any non-403 means CSRF dep passed.
    assert r.status_code != 403
