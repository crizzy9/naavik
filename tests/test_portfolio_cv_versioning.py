"""Plan 57 / 0.2.7.15 — `?version=v1` query param on `/api/portfolio/cv`.

Reserves a versioning surface so cv.astro on crypticsoul.dev can pin to a
known payload shape; future schema-breaking changes (renamed fields, EEO
policy edits) flip to `v2` without breaking existing fetches. Pydantic v2
`Literal["v1"]` validates the param; FastAPI returns 422 on unknown values.

Tests use a no-op DB stub (the underlying `get_cv` body runs the full
session.exec stack; we intercept via `app.dependency_overrides[get_session]`
to short-circuit before any actual DB call. The 404 branch when no Profile
row exists is the natural success-path assertion for the default-version
test — proves the route reached the body, which is downstream of the
Literal validator gate).
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.uses_sample_data_shims

os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")
os.environ.setdefault("NAAVIK_DEBUG", "1")


class _StubExec:
    """Mimic `session.exec(stmt)` returning an empty result."""

    def one_or_none(self):
        return None

    def all(self):
        return []

    def one(self):
        return (0,)


class _StubSession:
    """Minimum surface for `Depends(get_session)` — `exec` always returns
    an empty result; no Profile row → `get_cv` 404s naturally past the
    Literal validator. The point is exercising the param gate; the
    payload-build path is covered by `test_portfolio_sync.py`.
    """

    async def exec(self, stmt):  # noqa: D401
        return _StubExec()

    async def commit(self):  # pragma: no cover
        return None

    async def rollback(self):  # pragma: no cover
        return None

    async def close(self):  # pragma: no cover
        return None


async def _fake_get_session():
    yield _StubSession()


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from db.session import get_session
    from main import app

    app.dependency_overrides[get_session] = _fake_get_session
    yield TestClient(app, raise_server_exceptions=True)
    app.dependency_overrides.pop(get_session, None)


# ── default version (absent param → v1) ─────────────────────────────────


def test_get_cv_default_version_passes_validator(client):
    """No `version=` → defaults to `v1`; passes the Literal gate.

    Reaches the body, which 404s on the empty Profile stub. The 404 is
    downstream of the validator → the validator did NOT reject. Combined
    with `test_get_cv_explicit_v1_matches_default`, this proves the
    default-version contract.
    """
    r = client.get("/api/portfolio/cv")
    assert r.status_code == 404, r.text
    assert "profile not found" in r.json().get("detail", "").lower()


def test_get_cv_explicit_v1_matches_default(client):
    """Explicit `?version=v1` → identical behavior to default."""
    r = client.get("/api/portfolio/cv?version=v1")
    assert r.status_code == 404, r.text
    assert "profile not found" in r.json().get("detail", "").lower()


# ── unknown version → 422 (Pydantic Literal reject) ─────────────────────


def test_get_cv_unknown_version_rejected_with_422(client):
    """`?version=v999` → 422 from the Literal validator (not 404)."""
    r = client.get("/api/portfolio/cv?version=v999")
    assert r.status_code == 422, r.text
    body = r.json()
    # Pydantic v2 422 carries `detail` with a list of `{loc, msg, type, ...}`.
    assert "detail" in body
    locs = [d.get("loc") for d in body["detail"]]
    assert any("version" in loc for loc in locs), body


def test_get_cv_empty_version_rejected(client):
    """`?version=` (empty string) → 422 — empty isn't in the Literal set."""
    r = client.get("/api/portfolio/cv?version=")
    assert r.status_code == 422, r.text


def test_get_cv_arbitrary_string_rejected(client):
    """`?version=garbage` → 422 (defense against silent fallback)."""
    r = client.get("/api/portfolio/cv?version=garbage")
    assert r.status_code == 422, r.text
