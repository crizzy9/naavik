"""Settings · AI & Automation apply-resolver ops card render (2026-07).

Pins the read-only card: LinkedIn Tier-B session health chip states, the
refresh instructions when the session isn't ok, and graceful render when
stats are unavailable (sample-data shims run with session=None).
"""

from __future__ import annotations

import os  # noqa: I001

os.environ.setdefault("NAAVIK_DEBUG", "1")
os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

pytestmark = pytest.mark.uses_sample_data_shims


@pytest.fixture(scope="module")
def client() -> TestClient:
    from main import app

    c = TestClient(app, raise_server_exceptions=True)
    c.cookies.set("naavik_session", "fake-1")
    return c


def test_card_renders_not_logged_in_with_instructions(client, monkeypatch):
    from services import linkedin_resolver

    monkeypatch.setattr(
        linkedin_resolver,
        "read_session_health",
        lambda: {"status": "not_logged_in", "at": "2026-07-03T12:00:00+00:00", "alerted": True},
    )
    monkeypatch.setattr(linkedin_resolver, "auth_available", lambda: True)
    r = client.get("/settings/ai-automation")
    assert r.status_code == 200
    assert 'data-testid="apply-resolver-card"' in r.text
    assert "NOT LOGGED IN" in r.text
    assert "linkedin_login.py" in r.text
    assert "LINKEDIN_SESSION_COOKIE" in r.text


def test_card_renders_ok_without_instructions(client, monkeypatch):
    from services import linkedin_resolver

    monkeypatch.setattr(
        linkedin_resolver,
        "read_session_health",
        lambda: {"status": "ok", "at": "2026-07-03T12:00:00+00:00", "alerted": False},
    )
    monkeypatch.setattr(linkedin_resolver, "auth_available", lambda: True)
    r = client.get("/settings/ai-automation")
    assert r.status_code == 200
    assert "linkedin session · ok" in r.text
    assert "last authenticated attempt" in r.text
    assert "linkedin_login.py" not in r.text


def test_card_renders_not_configured_state(client, monkeypatch):
    from services import linkedin_resolver

    monkeypatch.setattr(linkedin_resolver, "read_session_health", lambda: None)
    monkeypatch.setattr(linkedin_resolver, "auth_available", lambda: False)
    r = client.get("/settings/ai-automation")
    assert r.status_code == 200
    assert "not configured" in r.text
    assert "Tier B (authenticated LinkedIn) is off" in r.text
