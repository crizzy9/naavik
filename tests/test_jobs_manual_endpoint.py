"""Plan 53 § B (0.2.4.02) — POST /api/v1/jobs/manual + modal route tests."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")
os.environ.setdefault("NAAVIK_DEBUG", "1")
os.environ["NAAVIK_PERSISTENCE"] = "memory"


_CSRF_TOKEN = "csrf-cookie-token-manual-job-aaaaaaaaaaaaaaaaaaaaaaa"


@pytest.fixture(scope="module")
def client() -> TestClient:
    from main import app

    c = TestClient(app, raise_server_exceptions=True)
    c.cookies.set("naavik_session", "fake-1")
    c.cookies.set("naavik_csrf", _CSRF_TOKEN)
    return c


def test_manual_job_modal_renders(client: TestClient) -> None:
    """GET /_modal/manual-job returns the modal partial with the form fields."""
    r = client.get("/_modal/manual-job")
    assert r.status_code == 200
    body = r.text
    assert 'id="manual-job-modal"' in body
    assert 'name="company"' in body
    assert 'name="role"' in body
    assert 'name="description"' in body
    assert 'name="url"' in body
    assert 'name="source"' in body
    assert 'name="remote_policy"' in body
    assert 'hx-post="/api/v1/jobs/manual"' in body


def test_post_manual_job_happy_path(client: TestClient, monkeypatch) -> None:
    """POST with full valid body → 204 + HX-Redirect: /tracking."""
    captured: dict = {}

    async def _fake_create(session, payload, *, user_id):
        captured["payload"] = payload
        captured["user_id"] = user_id
        from types import SimpleNamespace

        return SimpleNamespace(id=999)

    from services import job_service

    monkeypatch.setattr(job_service, "create_manual_job", _fake_create)

    r = client.post(
        "/api/v1/jobs/manual",
        data={
            "company": "Stripe",
            "role": "Senior Backend Engineer",
            "description": "Build payment infra at scale.",
            "url": "https://stripe.com/jobs/listing/123",
            "location": "Remote · NYC",
            "source": "manual",
            "remote_policy": "remote",
        },
        headers={"X-CSRF-Token": _CSRF_TOKEN},
    )
    assert r.status_code == 204
    assert r.headers.get("hx-redirect") == "/tracking"
    assert captured["payload"].company == "Stripe"
    assert captured["payload"].role == "Senior Backend Engineer"
    assert captured["payload"].url == "https://stripe.com/jobs/listing/123"
    assert captured["payload"].remote_policy.value == "remote"
    assert captured["payload"].board.value == "manual"


def test_post_manual_job_synthesizes_url_when_omitted(client: TestClient, monkeypatch) -> None:
    """Omitted URL gets a synthetic `manual://entry/<uuid>` so the unique
    index on (user_id, url) doesn't collide across URL-less manual entries.
    """
    captured: dict = {}

    async def _fake_create(session, payload, *, user_id):
        captured["payload"] = payload
        from types import SimpleNamespace

        return SimpleNamespace(id=1000)

    from services import job_service

    monkeypatch.setattr(job_service, "create_manual_job", _fake_create)

    r = client.post(
        "/api/v1/jobs/manual",
        data={
            "company": "Acme",
            "role": "Eng",
            "description": "JD",
        },
        headers={"X-CSRF-Token": _CSRF_TOKEN},
    )
    assert r.status_code == 204
    assert captured["payload"].url.startswith("manual://entry/")


def test_post_manual_job_rejects_missing_company(client: TestClient) -> None:
    """Form field validation — missing company returns 422 from FastAPI form parsing."""
    r = client.post(
        "/api/v1/jobs/manual",
        data={
            "role": "Eng",
            "description": "JD",
        },
        headers={"X-CSRF-Token": _CSRF_TOKEN},
    )
    assert r.status_code == 422


def test_post_manual_job_rejects_missing_description(client: TestClient) -> None:
    r = client.post(
        "/api/v1/jobs/manual",
        data={
            "company": "Acme",
            "role": "Eng",
        },
        headers={"X-CSRF-Token": _CSRF_TOKEN},
    )
    assert r.status_code == 422


def test_post_manual_job_rejects_blank_required_fields(client: TestClient) -> None:
    """Whitespace-only required fields collapse to '' after .strip() and 422."""
    r = client.post(
        "/api/v1/jobs/manual",
        data={
            "company": "   ",
            "role": "Eng",
            "description": "JD",
        },
        headers={"X-CSRF-Token": _CSRF_TOKEN},
    )
    assert r.status_code == 422
    assert "required" in r.text.lower()


def test_post_manual_job_rejects_invalid_remote_policy(client: TestClient) -> None:
    r = client.post(
        "/api/v1/jobs/manual",
        data={
            "company": "Acme",
            "role": "Eng",
            "description": "JD",
            "remote_policy": "bogus",
        },
        headers={"X-CSRF-Token": _CSRF_TOKEN},
    )
    assert r.status_code == 422


def test_post_manual_job_rejects_invalid_source(client: TestClient) -> None:
    r = client.post(
        "/api/v1/jobs/manual",
        data={
            "company": "Acme",
            "role": "Eng",
            "description": "JD",
            "source": "myspace",
        },
        headers={"X-CSRF-Token": _CSRF_TOKEN},
    )
    assert r.status_code == 422
    assert "invalid source" in r.text.lower()


def test_post_manual_job_unauthenticated_returns_401() -> None:
    """No session cookie → 401 from require_authed_session."""
    from main import app

    c = TestClient(app, raise_server_exceptions=True)
    r = c.post(
        "/api/v1/jobs/manual",
        data={
            "company": "Acme",
            "role": "Eng",
            "description": "JD",
        },
    )
    assert r.status_code == 401


def test_post_manual_job_missing_csrf_returns_403() -> None:
    """Session cookie present but no X-CSRF-Token header → 403 (hacker PR #153 HIGH-1)."""
    from main import app

    c = TestClient(app, raise_server_exceptions=True)
    c.cookies.set("naavik_session", "fake-1")
    c.cookies.set("naavik_csrf", _CSRF_TOKEN)
    r = c.post(
        "/api/v1/jobs/manual",
        data={
            "company": "Acme",
            "role": "Eng",
            "description": "JD",
        },
    )
    assert r.status_code == 403
    assert "csrf" in r.text.lower()


def test_post_manual_job_csrf_header_mismatch_returns_403() -> None:
    """X-CSRF-Token header value different from cookie → 403 (double-submit)."""
    from main import app

    c = TestClient(app, raise_server_exceptions=True)
    c.cookies.set("naavik_session", "fake-1")
    c.cookies.set("naavik_csrf", _CSRF_TOKEN)
    r = c.post(
        "/api/v1/jobs/manual",
        data={
            "company": "Acme",
            "role": "Eng",
            "description": "JD",
        },
        headers={"X-CSRF-Token": "wrong-token-value-zzzzzzzzzzzzzzzzzzzzzz"},
    )
    assert r.status_code == 403


def test_post_manual_job_rejects_javascript_url(client: TestClient) -> None:
    """`javascript:` URL scheme is rejected at JobCreate boundary (hacker PR #153 HIGH-2)."""
    r = client.post(
        "/api/v1/jobs/manual",
        data={
            "company": "Acme",
            "role": "Eng",
            "description": "JD",
            "url": "javascript:alert(document.cookie)",
        },
        headers={"X-CSRF-Token": _CSRF_TOKEN},
    )
    assert r.status_code == 422
    assert "scheme" in r.text.lower()


def test_post_manual_job_rejects_data_url(client: TestClient) -> None:
    """`data:` URL scheme is rejected (XSS vector via inline HTML)."""
    r = client.post(
        "/api/v1/jobs/manual",
        data={
            "company": "Acme",
            "role": "Eng",
            "description": "JD",
            "url": "data:text/html,<script>alert(1)</script>",
        },
        headers={"X-CSRF-Token": _CSRF_TOKEN},
    )
    assert r.status_code == 422
    assert "scheme" in r.text.lower()


def test_post_manual_job_rejects_file_url(client: TestClient) -> None:
    """`file:` URL scheme is rejected (local-file disclosure vector)."""
    r = client.post(
        "/api/v1/jobs/manual",
        data={
            "company": "Acme",
            "role": "Eng",
            "description": "JD",
            "url": "file:///etc/passwd",
        },
        headers={"X-CSRF-Token": _CSRF_TOKEN},
    )
    assert r.status_code == 422
    assert "scheme" in r.text.lower()


def test_post_manual_job_accepts_manual_synthetic_url(client: TestClient, monkeypatch) -> None:
    """`manual://entry/<id>` synthetic URLs pass validation (used when user omits URL)."""
    captured: dict = {}

    async def _fake_create(session, payload, *, user_id):
        captured["payload"] = payload
        from types import SimpleNamespace

        return SimpleNamespace(id=1001)

    from services import job_service

    monkeypatch.setattr(job_service, "create_manual_job", _fake_create)

    r = client.post(
        "/api/v1/jobs/manual",
        data={
            "company": "Acme",
            "role": "Eng",
            "description": "JD",
        },
        headers={"X-CSRF-Token": _CSRF_TOKEN},
    )
    assert r.status_code == 204
    assert captured["payload"].url.startswith("manual://entry/")


def test_tracking_page_add_manually_button_wires_modal(client: TestClient) -> None:
    """Tracking page's `Add manually` button HTMX-fetches the modal partial."""
    r = client.get("/tracking")
    assert r.status_code == 200
    assert 'hx-get="/_modal/manual-job"' in r.text
    assert "Add manually" in r.text
