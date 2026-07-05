"""Honest-submit guard (2026-07).

Jobs whose real application site can't be auto-submitted (LinkedIn Easy
Apply, Indeed, unresolved-external, Workday, …) used to dispatch to a stub
adapter and fail with a misleading "auth required" — so a Greenhouse posting
scraped off LinkedIn (apply site unresolved) reported as if it were LinkedIn.
The route now refuses cleanly with an explanatory toast + an `openApplyUrl`
trigger pointing at the real posting, and never reaches `submit_draft`.
"""

from __future__ import annotations

import json
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.uses_sample_data_shims

os.environ.setdefault("NAAVIK_DEBUG", "1")
os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")


@pytest.fixture
def client_with_user():
    from fastapi.testclient import TestClient

    from main import app
    from services.auth import require_password_complete

    user = SimpleNamespace(id=42, is_active=True, must_change_password=False)

    async def _override():
        return user

    app.dependency_overrides[require_password_complete] = _override
    # Routes now require CSRF (plan 91 Phase 1.6); thread a matching double-submit pair.
    _c = TestClient(app, raise_server_exceptions=True, headers={"X-CSRF-Token": "t"})
    _c.cookies.set("naavik_csrf", "t")
    yield _c, user
    app.dependency_overrides.pop(require_password_complete, None)


def _app_stub(board, job_id=7):
    from models import ApplicationBoard

    return SimpleNamespace(
        id=11,
        user_id=42,
        status="DRAFT",
        board=ApplicationBoard(board),
        job_id=job_id,
        deleted_at=None,
        external_url="https://www.linkedin.com/jobs/view/123",
    )


def _job_stub(apply_kind, apply_url=None):
    return SimpleNamespace(
        id=7,
        apply_kind=apply_kind,
        apply_url=apply_url,
        url="https://www.linkedin.com/jobs/view/123",
    )


def _submit(client, *, board, apply_kind, apply_url=None):
    submit_mock = AsyncMock()
    with (
        patch(
            "api.applications.svc.get_application",
            new=AsyncMock(return_value=_app_stub(board)),
        ),
        patch(
            "services.job_service.get_job",
            new=AsyncMock(return_value=_job_stub(apply_kind, apply_url)),
        ),
        patch("api.applications.svc.submit_draft", new=submit_mock),
    ):
        r = client.post("/api/v1/applications/11/submit")
    return r, submit_mock


def test_unresolved_external_refuses_without_dispatch(client_with_user):
    client, _ = client_with_user
    r, submit_mock = _submit(client, board="linkedin", apply_kind="external")
    assert r.status_code == 204
    submit_mock.assert_not_awaited()  # never dispatched to the stub adapter
    trig = json.loads(r.headers["HX-Trigger"])
    assert trig["showToast"]["tone"] == "info"
    assert "couldn't pin down" in trig["showToast"]["text"].lower()
    # The real posting is handed to the browser to open.
    assert trig["openApplyUrl"]["url"] == "https://www.linkedin.com/jobs/view/123"


def test_easy_apply_gets_linkedin_message(client_with_user):
    client, _ = client_with_user
    r, submit_mock = _submit(client, board="linkedin", apply_kind="easy_apply")
    assert r.status_code == 204
    submit_mock.assert_not_awaited()
    trig = json.loads(r.headers["HX-Trigger"])
    assert "Easy Apply" in trig["showToast"]["text"]


def test_supported_board_still_dispatches(client_with_user):
    """Greenhouse has a real adapter — the guard must NOT intercept it."""
    client, _ = client_with_user
    from services.applications import ValidationError

    submit_mock = AsyncMock(side_effect=ValidationError("boom", code="x"))
    with (
        patch(
            "api.applications.svc.get_application",
            new=AsyncMock(return_value=_app_stub("greenhouse")),
        ),
        patch("api.applications.svc.submit_draft", new=submit_mock),
    ):
        r = client.post("/api/v1/applications/11/submit")
    assert r.status_code == 409  # reached submit_draft
    submit_mock.assert_awaited_once()
