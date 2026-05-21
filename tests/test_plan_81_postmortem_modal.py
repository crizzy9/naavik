"""Plan 81 § D.1 (0.4.0.10) — postmortem modal route tests.

Covers:

- `GET /_modal/postmortem/<application_id>/<ts>` IDOR boundary (404 on
  cross-user / missing app) — never leak postmortem existence to non-owners.
- Path-traversal regex blocks `..` payloads → 404.
- Strict UTC-timestamp regex shape blocks malformed `ts` → 404.
- Happy path renders the postmortem-modal partial with analysis_md + trace.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")
os.environ.setdefault("NAAVIK_DEBUG", "1")


_CSRF_TOKEN = "csrf-cookie-token-plan-81-postmortem-aaaaaaaa"


@pytest.fixture
def client_with_user(tmp_path, monkeypatch) -> tuple[TestClient, SimpleNamespace]:
    """Bring up TestClient + override require_authed_session to a known user."""
    from config import settings as app_settings
    from services import ats_postmortem as svc_pm

    monkeypatch.setattr(app_settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(svc_pm.app_settings, "data_dir", str(tmp_path))

    from main import app
    from services.auth import require_authed_session

    user = SimpleNamespace(id=42, is_active=True, must_change_password=False)

    async def _override():
        return user

    app.dependency_overrides[require_authed_session] = _override
    c = TestClient(app, raise_server_exceptions=True)
    c.cookies.set("naavik_session", "fake-1")
    c.cookies.set("naavik_csrf", _CSRF_TOKEN)
    yield c, user
    app.dependency_overrides.pop(require_authed_session, None)


def _seed_postmortem(tmp_path: Path, *, application_id: int, ts: str) -> Path:
    base = tmp_path / "data" / "postmortems" / str(application_id) / ts
    base.mkdir(parents=True, exist_ok=True)
    (base / "trace.json").write_text(
        json.dumps({"application_id": application_id, "failure_kind": "auth_required"})
    )
    (base / "analysis.md").write_text("# postmortem\n\n**Classified as:** `auth_required`\n")
    return base


# ── Plan 81 § Test plan — IDOR + path-traversal ────────────────────────


def test_postmortem_modal_idor_cross_user_returns_404(client_with_user):
    """Application belongs to user 1; requester is user 42 → 404 (no leak)."""
    client, _user = client_with_user
    ts = "2026-05-20T10-12-51Z"
    other_app = SimpleNamespace(id=99, user_id=1)  # not our user
    with patch(
        "services.application_service.get_application",
        new=AsyncMock(return_value=other_app),
    ):
        r = client.get(f"/_modal/postmortem/99/{ts}")
    assert r.status_code == 404


def test_postmortem_modal_path_traversal_blocked(client_with_user):
    """ts containing path-traversal characters → strict regex rejects → 404."""
    client, user = client_with_user
    fake_app = SimpleNamespace(id=10, user_id=user.id)
    with patch(
        "services.application_service.get_application",
        new=AsyncMock(return_value=fake_app),
    ):
        # `..foo..bar` is one segment but doesn't match the \d{4}-... regex
        r = client.get("/_modal/postmortem/10/..foo..bar")
    assert r.status_code == 404


def test_postmortem_modal_malformed_ts_returns_404(client_with_user):
    """Non-timestamp `ts` → 404 (regex rejects everything except canonical)."""
    client, user = client_with_user
    fake_app = SimpleNamespace(id=10, user_id=user.id)
    with patch(
        "services.application_service.get_application",
        new=AsyncMock(return_value=fake_app),
    ):
        r = client.get("/_modal/postmortem/10/not-a-timestamp")
    assert r.status_code == 404


def test_postmortem_modal_missing_files_returns_404(client_with_user):
    """Valid regex but no postmortem on disk → 404."""
    client, user = client_with_user
    fake_app = SimpleNamespace(id=10, user_id=user.id)
    with patch(
        "services.application_service.get_application",
        new=AsyncMock(return_value=fake_app),
    ):
        r = client.get("/_modal/postmortem/10/2026-05-20T10-12-51Z")
    assert r.status_code == 404


def test_postmortem_modal_happy_path_renders(client_with_user, tmp_path):
    """Owner + seeded postmortem → 200 + partial markup."""
    client, user = client_with_user
    ts = "2026-05-20T10-12-51Z"
    _seed_postmortem(tmp_path, application_id=10, ts=ts)
    fake_app = SimpleNamespace(id=10, user_id=user.id)
    with patch(
        "services.application_service.get_application",
        new=AsyncMock(return_value=fake_app),
    ):
        r = client.get(f"/_modal/postmortem/10/{ts}")
    assert r.status_code == 200
    body = r.text
    assert 'data-testid="postmortem-modal"' in body
    assert "auth_required" in body
    # Raw-trace details element renders
    assert "Raw trace" in body
    # No HTML wrapper — fragment, not full page
    assert "<html" not in body.lower()
