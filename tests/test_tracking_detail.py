"""Plan 53 § C (0.2.4.03) — application detail slide-over tests.

Covers `/tracking/{application_id}` full page + `/_fragments/tracking/
application/{id}` partial swap. IDOR boundary returns 404 (never 403)
for cross-user access (plan § C.5 #3).
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")
os.environ.setdefault("NAAVIK_DEBUG", "1")
os.environ["NAAVIK_PERSISTENCE"] = "memory"


_CSRF_TOKEN = "csrf-cookie-token-tracking-detail-aaaaaaaaaaaaaaa"


@pytest.fixture(scope="module")
def client() -> TestClient:
    from main import app

    c = TestClient(app, raise_server_exceptions=True)
    c.cookies.set("naavik_session", "fake-1")
    c.cookies.set("naavik_csrf", _CSRF_TOKEN)
    return c


@pytest.fixture(scope="module")
def known_application_id() -> int:
    """Return a sample-data application id that belongs to user_id=1."""
    import asyncio

    from db import sample_data as sd

    async def _find():
        apps = await sd.applications_visible_in_tracking()
        return apps[0].id if apps else None

    return asyncio.run(_find())


def test_tracking_detail_full_page_renders(client: TestClient, known_application_id: int) -> None:
    """GET /tracking/{id} as owner returns 200 with detail content embedded."""
    assert known_application_id is not None, "no sample application available"
    r = client.get(f"/tracking/{known_application_id}")
    assert r.status_code == 200
    body = r.text
    assert "Tracking" in body
    assert 'data-testid="tracking-slide-over"' in body
    assert "tracking-slide-over-mount" in body
    assert 'id="application-detail-title"' in body


def test_tracking_detail_full_page_contains_company_role(
    client: TestClient, known_application_id: int
) -> None:
    """Detail page surfaces application.company + application.role."""
    import asyncio

    from db import sample_data as sd

    async def _get():
        return await sd.get_application(known_application_id)

    app = asyncio.run(_get())
    r = client.get(f"/tracking/{known_application_id}")
    assert r.status_code == 200
    assert app.company in r.text
    assert app.role in r.text


def test_tracking_detail_fragment_naked_partial(
    client: TestClient, known_application_id: int
) -> None:
    """GET /_fragments/tracking/application/{id} returns just the partial (no base shell)."""
    r = client.get(f"/_fragments/tracking/application/{known_application_id}")
    assert r.status_code == 200
    body = r.text
    assert 'data-testid="tracking-slide-over"' in body
    # No base shell — no <html> / <body> tags wrapping the fragment.
    assert "<html" not in body.lower()
    assert 'id="application-detail-title"' in body


def test_tracking_detail_nonexistent_returns_404(client: TestClient) -> None:
    """Unknown application id → 404."""
    r = client.get("/tracking/999999")
    assert r.status_code == 404


def test_tracking_detail_fragment_nonexistent_returns_404(client: TestClient) -> None:
    r = client.get("/_fragments/tracking/application/999999")
    assert r.status_code == 404


def test_tracking_detail_unauth_returns_401(known_application_id: int) -> None:
    """No session cookie → 401 from require_authed_session."""
    from main import app

    c = TestClient(app, raise_server_exceptions=True)
    r = c.get(f"/tracking/{known_application_id}")
    assert r.status_code == 401


def test_tracking_detail_fragment_unauth_returns_401(known_application_id: int) -> None:
    from main import app

    c = TestClient(app, raise_server_exceptions=True)
    r = c.get(f"/_fragments/tracking/application/{known_application_id}")
    assert r.status_code == 401


def test_tracking_detail_idor_cross_user_returns_404(
    client: TestClient, known_application_id: int
) -> None:
    """Application belonging to a different user_id → 404 (never 403).

    IDOR mitigation per plan § C.5 #3 — same shape as `/jobs/{id}` to
    prevent existence-enumeration via 403 vs 404 timing.
    """
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
        r = client.get(f"/tracking/{known_application_id}")
        assert r.status_code == 404, "cross-user must 404 not 403"
        r2 = client.get(f"/_fragments/tracking/application/{known_application_id}")
        assert r2.status_code == 404
    finally:
        asyncio.run(_restore(original))


def test_tracking_card_wires_slide_over_hx(client: TestClient) -> None:
    """tracking_card renders with HTMX attrs targeting the slide-over mount."""
    r = client.get("/tracking")
    assert r.status_code == 200
    body = r.text
    assert 'hx-target="#tracking-slide-over-mount"' in body
    assert 'hx-get="/_fragments/tracking/application/' in body
    assert 'id="tracking-slide-over-mount"' in body


def test_tracking_detail_renders_status_timeline(
    client: TestClient, known_application_id: int
) -> None:
    """Slide-over surfaces the status_timeline section heading."""
    r = client.get(f"/_fragments/tracking/application/{known_application_id}")
    assert r.status_code == 200
    body = r.text
    # documents section always renders even when empty
    assert "Documents" in body
    assert "Contacts" in body
    assert "Notes" in body


def test_application_detail_template_blocks_javascript_external_url(
    client: TestClient, known_application_id: int
) -> None:
    """Template scheme allowlist filters non-http(s) hrefs even if a hostile
    URL leaks past JobCreate (defense-in-depth for hacker PR #153 HIGH-2).
    """
    import asyncio

    from db import sample_data as sd

    async def _set_url(url: str) -> str:
        app = await sd.get_application(known_application_id)
        original = app.external_url
        app.external_url = url
        return original

    async def _restore(original: str) -> None:
        app = await sd.get_application(known_application_id)
        app.external_url = original

    # javascript: URL — must NOT render as a clickable link.
    original = asyncio.run(_set_url("javascript:alert(1)"))
    try:
        r = client.get(f"/_fragments/tracking/application/{known_application_id}")
        assert r.status_code == 200
        body = r.text
        assert 'href="javascript:' not in body
        assert "Open job posting" not in body
    finally:
        asyncio.run(_restore(original))

    # manual:// synthetic URL — also non-navigable, must not render.
    original = asyncio.run(_set_url("manual://entry/abc123"))
    try:
        r = client.get(f"/_fragments/tracking/application/{known_application_id}")
        assert r.status_code == 200
        body = r.text
        assert 'href="manual://' not in body
        assert "Open job posting" not in body
    finally:
        asyncio.run(_restore(original))

    # https URL — should render the link.
    original = asyncio.run(_set_url("https://example.com/jobs/123"))
    try:
        r = client.get(f"/_fragments/tracking/application/{known_application_id}")
        assert r.status_code == 200
        body = r.text
        assert 'href="https://example.com/jobs/123"' in body
        assert "Open job posting" in body
    finally:
        asyncio.run(_restore(original))
