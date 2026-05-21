"""Plan 71 (0.3.3.14): `/setup-help` first-run diagnostic page.

Public, unauthenticated route. Renders the three plan-10c first-run
signals (NAAVIK_DEBUG, user_count, dev-credentials artifact) + recovery
recipes. Reuses `services.first_run.probe_first_run_state`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


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
    """Diagnostic table surfaces all three signals."""
    r = client.get("/setup-help")
    assert r.status_code == 200
    body = r.text
    # The data-setup-help-diagnostic wrapper exists.
    assert "data-setup-help-diagnostic" in body
    # Each of the three signals has its own row.
    assert 'data-signal="debug"' in body
    assert 'data-signal="users"' in body
    assert 'data-signal="dev-credentials"' in body
    # Each signal references its source.
    assert "NAAVIK_DEBUG" in body
    assert "user_count" in body
    assert "dev-credentials" in body


def test_setup_help_renders_recovery_recipes(client: TestClient):
    """Recovery section lists `nix run .#dev` + manual env-var + drop-+-reseed."""
    r = client.get("/setup-help")
    assert r.status_code == 200
    body = r.text
    assert "data-setup-help-recipes" in body
    assert "nix run .#dev" in body
    assert "NAAVIK_DEBUG=1" in body
    # Destructive recipe is labeled and references the data dir + dev-credentials path.
    assert "destructive" in body.lower()
    assert "dev-credentials" in body


def test_setup_help_links_to_runbook_section(client: TestClient):
    """Both inline + footer link to the new RUNBOOK § first-run section."""
    r = client.get("/setup-help")
    assert r.status_code == 200
    # The anchor matches `_RUNBOOK_ANCHOR` in `src/ui/routes/setup_help.py`.
    assert "212-first-run-authentication--401-troubleshooting" in r.text


def test_setup_help_renders_broken_card_when_state_broken(client: TestClient, monkeypatch):
    """Broken trifecta → amber 'Locked out' info card surfaces."""
    from services import first_run

    fake_state = first_run.FirstRunState(
        debug_enabled=False,
        user_count=1,
        dev_credentials_present=False,
        dev_credentials_path="/tmp/.naavik/dev-credentials",
    )

    async def _fake_probe(session):
        return fake_state

    monkeypatch.setattr(first_run, "probe_first_run_state", _fake_probe)

    r = client.get("/setup-help")
    assert r.status_code == 200
    body = r.text
    assert "Locked out" in body
    # The amber tone comes from the info_card warning variant.
    assert "amber" in body


def test_setup_help_renders_healthy_card_when_creds_present(client: TestClient, monkeypatch):
    """When dev-credentials file is present → green success card."""
    from services import first_run

    fake_state = first_run.FirstRunState(
        debug_enabled=True,
        user_count=1,
        dev_credentials_present=True,
        dev_credentials_path="/tmp/.naavik/dev-credentials",
    )

    async def _fake_probe(session):
        return fake_state

    monkeypatch.setattr(first_run, "probe_first_run_state", _fake_probe)

    r = client.get("/setup-help")
    assert r.status_code == 200
    body = r.text
    assert "dev-credentials file present" in body


def test_setup_help_renders_fresh_install_card_when_no_users(client: TestClient, monkeypatch):
    """When no User row exists → signup-prompt info card."""
    from services import first_run

    fake_state = first_run.FirstRunState(
        debug_enabled=False,
        user_count=0,
        dev_credentials_present=False,
        dev_credentials_path="/tmp/.naavik/dev-credentials",
    )

    async def _fake_probe(session):
        return fake_state

    monkeypatch.setattr(first_run, "probe_first_run_state", _fake_probe)

    r = client.get("/setup-help")
    assert r.status_code == 200
    body = r.text
    assert "Fresh install" in body
    assert "/login?mode=signup" in body
