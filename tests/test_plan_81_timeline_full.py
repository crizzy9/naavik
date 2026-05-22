"""Plan 81 § D.2 (0.4.0.12) — full AppEvent timeline fragment tests.

Covers:

- `GET /_fragments/tracking/timeline/<id>` IDOR boundary (404 cross-user).
- Happy path returns the full-history partial w/ events from the
  per-kind icon map (status_change + docs_failed etc.).
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.uses_sample_data_shims

os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")
os.environ.setdefault("NAAVIK_DEBUG", "1")


_CSRF_TOKEN = "csrf-cookie-token-plan-81-timeline-bbbbbbbb"


@pytest.fixture(scope="module")
def client() -> TestClient:
    from main import app

    c = TestClient(app, raise_server_exceptions=True)
    c.cookies.set("naavik_session", "fake-1")
    c.cookies.set("naavik_csrf", _CSRF_TOKEN)
    return c


@pytest.fixture(scope="module")
def known_application_id() -> int:
    """A user-1 application id w/ at least one AppEvent in sample data."""
    import asyncio

    from db import sample_data as sd

    async def _find():
        for a in sd.APPLICATIONS:
            if a.user_id == 1 and a.deleted_at is None:
                events = [e for e in sd.APP_EVENTS if e.application_id == a.id]
                if events:
                    return a.id
        return None

    return asyncio.run(_find())


def test_timeline_fragment_returns_full_history(
    client: TestClient, known_application_id: int
) -> None:
    """GET /_fragments/tracking/timeline/<id> renders the full-history partial."""
    assert known_application_id is not None, "no sample application with events"
    r = client.get(f"/_fragments/tracking/timeline/{known_application_id}")
    assert r.status_code == 200
    body = r.text
    assert 'data-testid="detail-status-timeline-full"' in body
    assert "Full history" in body
    # Per-kind labels come from the renderer; STATUS_CHANGE label or kind tag.
    assert "status_change" in body or "→" in body


def test_timeline_fragment_idor_cross_user_returns_404(
    client: TestClient, known_application_id: int
) -> None:
    """Cross-user application → 404 (never 403)."""
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
        r = client.get(f"/_fragments/tracking/timeline/{known_application_id}")
        assert r.status_code == 404
    finally:
        asyncio.run(_restore(original))


def test_timeline_fragment_nonexistent_application_returns_404(client: TestClient) -> None:
    r = client.get("/_fragments/tracking/timeline/999999")
    assert r.status_code == 404


def test_detail_renders_show_full_history_toggle(
    client: TestClient, known_application_id: int
) -> None:
    """Slide-over surfaces the 'Show full history' HTMX toggle."""
    r = client.get(f"/_fragments/tracking/application/{known_application_id}")
    assert r.status_code == 200
    body = r.text
    assert 'data-testid="timeline-show-full"' in body
    assert f'hx-get="/_fragments/tracking/timeline/{known_application_id}"' in body
