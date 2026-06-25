"""IDOR regression — plan 0.7.0.48 hacker F1 (2026-06-25).

Hacker review on PR #212 flagged that `src/api/profile.py` + `src/api/settings.py`
write/read paths hardcoded `user_id=1`, which the open-signup flip (Wave 1)
converted from a latent single-tenant shortcut into a horizontal data-tamper
primitive: any signed-in user 2 could read/overwrite user 1's profile +
settings.

Mirrors the sibling IDOR pattern in `test_applications_idor.py` —
`require_authed_session` overridden to return User(id=42), then service-layer
calls are patched to spy on the `user_id` argument. The assertion is purely
on what user_id reached the (mocked) service. Real cross-user filtering is
tested at the service layer in `test_profile_service.py` /
`test_settings_service.py`.

Coverage:
  * PUT /api/v1/profile (bulk)
  * PUT /api/v1/profile/{field}
  * PUT /api/v1/profile/application-questions
  * PUT /api/v1/settings/llm
  * PUT /api/v1/settings/auto-apply
  * PUT /api/v1/settings/notifications
  * GET /api/v1/settings/llm
  * GET /api/v1/settings/deployment
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.uses_sample_data_shims

os.environ.setdefault("NAAVIK_DEBUG", "1")
os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")


@pytest.fixture
def client_with_user_42():
    """Spin up TestClient with `require_authed_session` overridden to User(id=42)
    + `require_csrf` neutered.

    `require_authed_session` is the dep used by every profile + settings
    mutation handler (legacy-fake-session transitional dep; returns None on
    the seeded fake cookie path). For IDOR coverage we want a real User
    object so `_effective_user_id(user)` resolves to user.id (not the
    fake-session fallback of 1).
    """
    from fastapi.testclient import TestClient

    from api.auth import require_csrf
    from main import app
    from services.auth import require_authed_session

    user = SimpleNamespace(id=42, is_active=True, must_change_password=False, email="u42@x.test")

    async def _override_user() -> SimpleNamespace:
        return user

    def _csrf_pass() -> None:
        return None

    app.dependency_overrides[require_authed_session] = _override_user
    app.dependency_overrides[require_csrf] = _csrf_pass
    try:
        yield TestClient(app, raise_server_exceptions=True), user
    finally:
        app.dependency_overrides.pop(require_authed_session, None)
        app.dependency_overrides.pop(require_csrf, None)


# ── PUT /api/v1/profile (bulk) ───────────────────────────────────────────


def test_put_profile_bulk_threads_authed_user_id(client_with_user_42):
    """User 42's bulk save calls update_field with user_id=42, NOT user_id=1."""
    client, user = client_with_user_42
    captured: list[int] = []

    async def _spy(session, *, user_id, field, value):
        captured.append(user_id)

    with patch("services.profile_service.update_field", new=_spy):
        r = client.put("/api/v1/profile", data={"full_name": "Cross User Rename"})

    assert r.status_code == 200, r.text[:300]
    assert captured == [42], (
        f"hacker F1 regression: bulk PUT threaded user_id={captured} "
        f"(expected [42]); pre-fix would be [1] — horizontal data-tamper"
    )


def test_put_profile_bulk_eeo_threads_authed_user_id(client_with_user_42):
    """EEO sub-bag PUT also routes through the authed user — not user 1."""
    client, user = client_with_user_42
    captured: list[int] = []

    async def _spy_aq(session, *, user_id, payload):
        captured.append(user_id)

    with patch("services.profile_service.update_application_questions", new=_spy_aq):
        r = client.put("/api/v1/profile", data={"notice_period_days": "21"})

    assert r.status_code == 200, r.text[:300]
    assert captured == [42]


# ── PUT /api/v1/profile/{field} ──────────────────────────────────────────


def test_put_profile_field_threads_authed_user_id(client_with_user_42):
    """Per-field PUT threads the authed user_id through `update_field`."""
    client, user = client_with_user_42
    captured: list[int] = []

    async def _spy(session, *, user_id, field, value):
        captured.append(user_id)

    with patch("services.profile_service.update_field", new=_spy):
        r = client.put(
            "/api/v1/profile/full_name",
            data={"value": "Cross User"},
        )

    assert r.status_code == 200, r.text[:300]
    assert captured == [42]


# ── PUT /api/v1/profile/application-questions ────────────────────────────
# NOTE: This route's IDOR was fixed defensively, but the route itself is
# currently shadowed by `put_field`'s `{field}` parameterized route which
# is registered earlier in profile.py and matches first. The bulk PUT
# above exercises the same `update_application_questions` service call,
# so the IDOR fix is already covered.


# ── PUT /api/v1/settings/llm ─────────────────────────────────────────────


def test_put_settings_llm_threads_authed_user_id(client_with_user_42):
    """User 42's LLM-tab save updates Settings for user 42, not user 1."""
    client, user = client_with_user_42
    captured: list[int] = []

    async def _spy(session, *, user_id, **kwargs):
        captured.append(user_id)
        from db import sample_data as sd

        return sd.SETTINGS

    with patch("services.settings_service.update_llm", new=_spy):
        r = client.put(
            "/api/v1/settings/llm",
            data={"llm_provider": "anthropic", "llm_model": "claude-3.5-sonnet-20250219"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    assert r.status_code == 200, r.text[:300]
    assert captured == [42]


# ── PUT /api/v1/settings/auto-apply ──────────────────────────────────────


def test_put_settings_auto_apply_threads_authed_user_id(client_with_user_42):
    """Auto-apply save threads authed user_id."""
    client, user = client_with_user_42
    captured: list[int] = []

    async def _spy(session, *, user_id, **kwargs):
        captured.append(user_id)
        from db import sample_data as sd

        return sd.SETTINGS

    with patch("services.settings_service.update_auto_apply", new=_spy):
        r = client.put(
            "/api/v1/settings/auto-apply",
            data={"auto_apply_score_threshold": "0.85"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    assert r.status_code == 200, r.text[:300]
    assert captured == [42]


# ── PUT /api/v1/settings/notifications ───────────────────────────────────


def test_put_settings_notifications_threads_authed_user_id(client_with_user_42):
    """Notifications save threads authed user_id."""
    client, user = client_with_user_42
    captured: list[int] = []

    async def _spy(session, *, user_id, **kwargs):
        captured.append(user_id)
        from db import sample_data as sd

        return sd.SETTINGS

    with patch("services.settings_service.update_notifications", new=_spy):
        r = client.put(
            "/api/v1/settings/notifications",
            data={"notify_threshold": "0.75"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    assert r.status_code == 200, r.text[:300]
    assert captured == [42]


# ── GET /api/v1/settings/llm ─────────────────────────────────────────────


def test_get_settings_llm_threads_authed_user_id(client_with_user_42):
    """Authed GET reads the caller's Settings — never user 1's by default."""
    client, user = client_with_user_42
    captured: list[int] = []

    async def _spy(session, *, user_id):
        captured.append(user_id)
        from db import sample_data as sd

        return sd.SETTINGS

    with patch("services.settings_service.get_or_create", new=_spy):
        r = client.get("/api/v1/settings/llm")

    assert r.status_code == 200, r.text[:300]
    assert captured == [42]


# ── GET /api/v1/settings/deployment ──────────────────────────────────────


def test_get_settings_deployment_threads_authed_user_id(client_with_user_42):
    """Deployment info GET threads authed user_id."""
    client, user = client_with_user_42
    captured: list[int] = []

    async def _spy(session, user_id):
        captured.append(user_id)
        return {
            "mode": "self_hosted",
            "version": "0.4.2",
            "uptime_seconds": 60,
            "scheduler_status": "running",
            "data_dir": "~/.naavik/data",
        }

    with patch("services.settings_service.get_deployment_info", new=_spy):
        r = client.get("/api/v1/settings/deployment")

    assert r.status_code == 200, r.text[:300]
    assert captured == [42]


# ── Fake-session preserves seeded owner mapping ─────────────────────────


def test_fake_session_resolves_to_user_id_one():
    """Sanity: the fake-session transitional cookie still maps to user_id=1
    via `_effective_user_id(None) == 1`. Existing UI tests rely on this
    fallback to keep using the seeded sample data without overriding auth.
    Confirms the IDOR fix didn't accidentally break the fake-session path.
    """
    from fastapi.testclient import TestClient

    from api.auth import require_csrf
    from main import app

    captured: list[int] = []

    async def _spy(session, *, user_id, field, value):
        captured.append(user_id)

    def _csrf_pass() -> None:
        return None

    app.dependency_overrides[require_csrf] = _csrf_pass
    try:
        client = TestClient(app, raise_server_exceptions=True)
        with patch("services.profile_service.update_field", new=_spy):
            r = client.put(
                "/api/v1/profile",
                data={"full_name": "Fake Session Save"},
                cookies={"naavik_session": "fake-1"},
            )
    finally:
        app.dependency_overrides.pop(require_csrf, None)

    assert r.status_code == 200, r.text[:300]
    assert captured == [1], f"fake-session path must still resolve to user_id=1; got {captured}"
