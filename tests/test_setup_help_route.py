"""Plan 83 (0.7.0.36): `/setup-help` first-run diagnostic page.

Public, unauthenticated route. After plan 83 the page surfaces a single
user_count signal + the "visit /signup" recovery recipe — no
dev-credentials artifact, no NAAVIK_DEBUG gate.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.uses_sample_data_shims


@pytest.fixture(scope="module")
def client() -> TestClient:
    from main import app

    return TestClient(app, raise_server_exceptions=True)


def test_setup_help_route_is_public_no_auth_required(client: TestClient):
    """`GET /setup-help` returns 200 without any session cookie."""
    r = client.get("/setup-help")
    assert r.status_code == 200
    assert "Setup help" in r.text


def test_setup_help_renders_diagnostic_table(client: TestClient):
    """Diagnostic table surfaces the user_count signal."""
    r = client.get("/setup-help")
    assert r.status_code == 200
    body = r.text
    assert "data-setup-help-diagnostic" in body
    assert 'data-signal="users"' in body
    assert "user_count" in body


def test_setup_help_renders_recovery_recipes(client: TestClient):
    """Recovery section lists /signup CTA + orchestrator-logs + reset recipes."""
    r = client.get("/setup-help")
    assert r.status_code == 200
    body = r.text
    assert "data-setup-help-recipes" in body
    assert "/signup" in body
    assert "nix run .#dev" in body
    assert "destructive" in body.lower()


def test_setup_help_links_to_runbook_section(client: TestClient):
    """Footer link points at the RUNBOOK § first-run section."""
    r = client.get("/setup-help")
    assert r.status_code == 200
    assert "212-first-run-authentication--401-troubleshooting" in r.text


def test_setup_help_renders_fresh_install_card_when_no_users(client: TestClient, monkeypatch):
    """When no User row exists → signup-prompt info card."""
    from services import first_run

    fake_state = first_run.FirstRunState(user_count=0)

    async def _fake_probe(session):
        return fake_state

    monkeypatch.setattr(first_run, "probe_first_run_state", _fake_probe)

    r = client.get("/setup-help")
    assert r.status_code == 200
    body = r.text
    assert "Fresh install" in body
    assert "/login?mode=signup" in body


def test_setup_help_renders_signed_in_card_when_users_present(client: TestClient, monkeypatch):
    """When a User row exists → 'sign in at /login' info card."""
    from services import first_run

    fake_state = first_run.FirstRunState(user_count=1)

    async def _fake_probe(session):
        return fake_state

    monkeypatch.setattr(first_run, "probe_first_run_state", _fake_probe)

    r = client.get("/setup-help")
    assert r.status_code == 200
    body = r.text
    assert "An account exists" in body
