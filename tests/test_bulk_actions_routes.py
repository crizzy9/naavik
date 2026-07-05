"""Plan 80 / 0.4.0.09 — bulk-action route tests on /tracking list view.

Covers the three new endpoints:
- POST /_fragments/tracking/bulk/move-stage
- POST /_fragments/tracking/bulk/archive
- GET  /api/v1/applications/export.csv
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.uses_sample_data_shims

os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")
os.environ.setdefault("NAAVIK_DEBUG", "1")


_CSRF_TOKEN = "csrf-cookie-token-bulk-actions-bbbbbbbbbbbbbbbbbbbbb"


@pytest.fixture(scope="module")
def client() -> TestClient:
    from main import app

    c = TestClient(app, raise_server_exceptions=True)
    c.cookies.set("naavik_session", "fake-1")
    c.cookies.set("naavik_csrf", _CSRF_TOKEN)
    return c


def _stub_tracking_ctx(monkeypatch) -> None:
    """Route handlers re-render the list fragment after mutation. Stub the
    ctx builder to keep tests focused on header + status assertions.
    """
    from ui import tracking_ctx as tctx

    async def _fake_ctx(session, *, user_id, view, show_closed=False, show_drafts=False):
        return {
            "view": view,
            "rows": [],
            "active_sidebar": "tracking",
            "active_template_path": "/tracking",
        }

    monkeypatch.setattr(tctx, "build_tracking_ctx", _fake_ctx)


# ── bulk move-stage ─────────────────────────────────────────────────


def test_bulk_move_stage_happy_path(client: TestClient, monkeypatch) -> None:
    """Valid IDs + status → 200 + HX-Trigger showToast w/ success summary."""
    _stub_tracking_ctx(monkeypatch)
    from services import applications as application_service

    async def _fake_bulk(session, *, user_id, application_ids, new_status, closed_reason=None):
        return (2, [])

    monkeypatch.setattr(application_service, "bulk_update_status", _fake_bulk)

    r = client.post(
        "/_fragments/tracking/bulk/move-stage",
        data={
            "application_ids": [1, 2],
            "new_status": "RECRUITER_SCREEN",
        },
        headers={"X-CSRF-Token": _CSRF_TOKEN},
    )
    assert r.status_code == 200
    trigger = r.headers.get("hx-trigger", "")
    assert "showToast" in trigger
    assert '"Updated 2, skipped 0"' in trigger


def test_bulk_move_stage_partial_failure_surfaces_skipped(client: TestClient, monkeypatch) -> None:
    """Mixed success + skip → toast reports both counts."""
    _stub_tracking_ctx(monkeypatch)
    from services import applications as application_service

    async def _fake_bulk(session, *, user_id, application_ids, new_status, closed_reason=None):
        return (1, [99])

    monkeypatch.setattr(application_service, "bulk_update_status", _fake_bulk)

    r = client.post(
        "/_fragments/tracking/bulk/move-stage",
        data={
            "application_ids": [1, 99],
            "new_status": "RECRUITER_SCREEN",
        },
        headers={"X-CSRF-Token": _CSRF_TOKEN},
    )
    assert r.status_code == 200
    assert '"Updated 1, skipped 1"' in r.headers.get("hx-trigger", "")


def test_bulk_move_stage_rejects_unknown_status(client: TestClient, monkeypatch) -> None:
    """Bad enum value → 422; service never reached."""
    called = SimpleNamespace(hit=False)

    async def _fake_bulk(*a, **k):
        called.hit = True
        return (0, [])

    from services import applications as application_service

    monkeypatch.setattr(application_service, "bulk_update_status", _fake_bulk)

    r = client.post(
        "/_fragments/tracking/bulk/move-stage",
        data={
            "application_ids": [1],
            "new_status": "NOT_A_REAL_STATUS",
        },
        headers={"X-CSRF-Token": _CSRF_TOKEN},
    )
    assert r.status_code == 422
    assert called.hit is False


def test_bulk_move_stage_rejects_over_cap(client: TestClient, monkeypatch) -> None:
    """Service raises bulk_limit_exceeded → route returns 422."""
    _stub_tracking_ctx(monkeypatch)
    from services import applications as application_service

    async def _fake_bulk(*a, **k):
        raise application_service.ValidationError(
            "Bulk operation limit is 50 applications per request",
            code="bulk_limit_exceeded",
        )

    monkeypatch.setattr(application_service, "bulk_update_status", _fake_bulk)

    r = client.post(
        "/_fragments/tracking/bulk/move-stage",
        data={
            "application_ids": list(range(1, 52)),
            "new_status": "RECRUITER_SCREEN",
        },
        headers={"X-CSRF-Token": _CSRF_TOKEN},
    )
    assert r.status_code == 422


def test_bulk_move_stage_requires_csrf(client: TestClient, monkeypatch) -> None:
    """Missing X-CSRF-Token header → 403, service never called."""
    called = SimpleNamespace(hit=False)

    async def _fake_bulk(*a, **k):
        called.hit = True
        return (0, [])

    from services import applications as application_service

    monkeypatch.setattr(application_service, "bulk_update_status", _fake_bulk)

    r = client.post(
        "/_fragments/tracking/bulk/move-stage",
        data={"application_ids": [1], "new_status": "RECRUITER_SCREEN"},
    )
    assert r.status_code == 403
    assert called.hit is False


# ── bulk archive ────────────────────────────────────────────────────


def test_bulk_archive_happy_path(client: TestClient, monkeypatch) -> None:
    """Valid IDs → 200 + HX-Trigger toast; bulk_archive received the IDs."""
    _stub_tracking_ctx(monkeypatch)
    captured: dict = {}

    async def _fake_archive(session, *, user_id, application_ids):
        captured["ids"] = list(application_ids)
        captured["user_id"] = user_id
        return (len(application_ids), [])

    from services import applications as application_service

    monkeypatch.setattr(application_service, "bulk_archive", _fake_archive)

    r = client.post(
        "/_fragments/tracking/bulk/archive",
        data={"application_ids": [3, 4, 5]},
        headers={"X-CSRF-Token": _CSRF_TOKEN},
    )
    assert r.status_code == 200
    assert captured["ids"] == [3, 4, 5]
    assert '"Updated 3, skipped 0"' in r.headers.get("hx-trigger", "")


# ── CSV export ──────────────────────────────────────────────────────


def test_bulk_export_csv_attachment_headers_and_columns(client: TestClient, monkeypatch) -> None:
    """GET export.csv returns text/csv attachment w/ canonical 10 columns."""
    from services import applications as application_service

    async def _fake_list(session, *, user_id, application_ids):
        return [
            {
                "company": "Stripe",
                "role": "Senior Backend Engineer",
                "team": "",
                "location": "Remote",
                "status": "APPLIED",
                "applied_at": "2026-05-21T00:00:00+00:00",
                "salary_min": 180000,
                "salary_max": 240000,
                "board": "greenhouse",
                "external_url": "https://example/jobs/1",
            }
        ]

    monkeypatch.setattr(application_service, "list_for_export", _fake_list)

    r = client.get("/api/v1/applications/export.csv?application_ids=1")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert r.headers["content-disposition"] == 'attachment; filename="applications.csv"'
    body = r.text.strip().splitlines()
    # Header line + 1 data row.
    assert len(body) == 2
    assert body[0] == (
        "company,role,team,location,status,applied_at,salary_min,salary_max,board,external_url"
    )
    assert "Stripe" in body[1]
    assert "180000" in body[1]


def test_bulk_export_csv_filters_cross_user(client: TestClient, monkeypatch) -> None:
    """list_for_export's WHERE filter strips cross-user IDs — CSV omits them."""
    from services import applications as application_service

    async def _fake_list(session, *, user_id, application_ids):
        # Caller passes [10, 99]; only 10 belongs to user 1.
        return [
            {
                "company": "Acme",
                "role": "Eng",
                "team": "",
                "location": "",
                "status": "APPLIED",
                "applied_at": "",
                "salary_min": "",
                "salary_max": "",
                "board": "",
                "external_url": "",
            }
        ]

    monkeypatch.setattr(application_service, "list_for_export", _fake_list)

    r = client.get("/api/v1/applications/export.csv?application_ids=10&application_ids=99")
    assert r.status_code == 200
    body = r.text
    assert "Acme" in body
    # Only 1 data row beyond the header.
    assert len([ln for ln in body.strip().splitlines() if ln]) == 2
