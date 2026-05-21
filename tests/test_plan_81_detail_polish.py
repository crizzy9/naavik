"""Plan 81 § D.3 (0.4.0.16) — application detail polish tests.

Covers:

- `PUT /api/v1/applications/<id>/notes` happy path (form-encoded + JSON).
- IDOR boundary on the same route (cross-user → 404, never 403).
- CSRF missing → 403.
- Notes overflow → 422.
- Discover-review jump link rendered for DRAFT-with-job applications.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")
os.environ.setdefault("NAAVIK_DEBUG", "1")


_CSRF_TOKEN = "csrf-cookie-token-plan-81-polish-cccccccc"


@pytest.fixture(scope="module")
def client() -> TestClient:
    from main import app

    c = TestClient(app, raise_server_exceptions=True)
    c.cookies.set("naavik_session", "fake-1")
    c.cookies.set("naavik_csrf", _CSRF_TOKEN)
    return c


@pytest.fixture(scope="module")
def known_application_id() -> int:
    """An APPLIED user-1 application (non-DRAFT, has notes-editable surface)."""
    import asyncio

    from db import sample_data as sd
    from models.enums import ApplicationStatus

    async def _find():
        for a in sd.APPLICATIONS:
            if a.user_id == 1 and a.deleted_at is None and a.status != ApplicationStatus.DRAFT:
                return a.id
        return None

    return asyncio.run(_find())


@pytest.fixture(scope="module")
def known_draft_application_id() -> int:
    """A DRAFT user-1 application with job_id set (for Discover jump link)."""
    import asyncio

    from db import sample_data as sd
    from models.enums import ApplicationStatus

    async def _find():
        for a in sd.APPLICATIONS:
            if (
                a.user_id == 1
                and a.deleted_at is None
                and a.status == ApplicationStatus.DRAFT
                and a.job_id is not None
            ):
                return a.id
        return None

    return asyncio.run(_find())


# ── PUT /api/v1/applications/{id}/notes ──


def test_notes_update_happy_path_form_encoded(
    client: TestClient, known_application_id: int
) -> None:
    """Form-encoded PUT updates notes; returns 204."""
    import asyncio

    from db import sample_data as sd

    async def _get_app():
        return await sd.get_application(known_application_id)

    new_text = "Plan 81 test note — autosave verification"
    r = client.put(
        f"/api/v1/applications/{known_application_id}/notes",
        data={"notes": new_text},
        headers={"X-CSRF-Token": _CSRF_TOKEN},
    )
    assert r.status_code == 204, r.text
    a = asyncio.run(_get_app())
    assert a.notes == new_text


def test_notes_update_happy_path_json(client: TestClient, known_application_id: int) -> None:
    """JSON-encoded PUT also accepted (machine consumers)."""
    import asyncio

    from db import sample_data as sd

    async def _get_app():
        return await sd.get_application(known_application_id)

    new_text = "Plan 81 — JSON body path"
    r = client.put(
        f"/api/v1/applications/{known_application_id}/notes",
        json={"notes": new_text},
        headers={"X-CSRF-Token": _CSRF_TOKEN},
    )
    assert r.status_code == 204, r.text
    a = asyncio.run(_get_app())
    assert a.notes == new_text


def test_notes_update_csrf_missing_rejects(client: TestClient, known_application_id: int) -> None:
    """Mutating PUT without X-CSRF-Token → 403."""
    r = client.put(
        f"/api/v1/applications/{known_application_id}/notes",
        data={"notes": "no csrf"},
    )
    assert r.status_code == 403


def test_notes_update_overflow_rejects(client: TestClient, known_application_id: int) -> None:
    """Notes over 2000 chars → 422."""
    big = "x" * 2001
    r = client.put(
        f"/api/v1/applications/{known_application_id}/notes",
        data={"notes": big},
        headers={"X-CSRF-Token": _CSRF_TOKEN},
    )
    assert r.status_code == 422


def test_notes_update_idor_cross_user_returns_404(
    client: TestClient, known_application_id: int
) -> None:
    """Cross-user PUT → 404 (never 403). Non-mutating test (404 before write)."""
    import asyncio

    from db import sample_data as sd

    async def _set_foreign():
        app = await sd.get_application(known_application_id)
        original = app.user_id
        app.user_id = 9999
        return original

    async def _restore(original):
        app = await sd.get_application(known_application_id)
        app.user_id = original

    original = asyncio.run(_set_foreign())
    try:
        r = client.put(
            f"/api/v1/applications/{known_application_id}/notes",
            data={"notes": "should never land"},
            headers={"X-CSRF-Token": _CSRF_TOKEN},
        )
        assert r.status_code == 404
    finally:
        asyncio.run(_restore(original))


def test_notes_update_missing_field_rejects(client: TestClient, known_application_id: int) -> None:
    """Missing `notes` field → 422."""
    r = client.put(
        f"/api/v1/applications/{known_application_id}/notes",
        json={"other": "x"},
        headers={"X-CSRF-Token": _CSRF_TOKEN},
    )
    assert r.status_code == 422


# ── Discover-review jump link for DRAFT applications ──


def test_detail_renders_discover_jump_link_for_draft(
    client: TestClient, known_draft_application_id: int
) -> None:
    """DRAFT with job_id surfaces the Continue-editing-on-Discover link."""
    assert known_draft_application_id is not None, "no sample DRAFT w/ job_id"
    r = client.get(f"/_fragments/tracking/application/{known_draft_application_id}")
    assert r.status_code == 200
    body = r.text
    assert 'data-testid="detail-discover-jump"' in body
    assert "Continue editing on Discover" in body


def test_detail_does_not_render_discover_jump_for_applied(
    client: TestClient, known_application_id: int
) -> None:
    """APPLIED (non-DRAFT) → no Discover jump link."""
    r = client.get(f"/_fragments/tracking/application/{known_application_id}")
    assert r.status_code == 200
    assert 'data-testid="detail-discover-jump"' not in r.text


# ── Notes textarea HTMX attrs ──


def test_detail_notes_textarea_has_blur_autosave_attrs(
    client: TestClient, known_application_id: int
) -> None:
    """Slide-over notes textarea wires hx-put + blur trigger."""
    r = client.get(f"/_fragments/tracking/application/{known_application_id}")
    assert r.status_code == 200
    body = r.text
    assert 'data-testid="detail-notes-textarea"' in body
    assert f'hx-put="/api/v1/applications/{known_application_id}/notes"' in body
    assert 'hx-trigger="blur changed"' in body
    assert 'maxlength="2000"' in body
