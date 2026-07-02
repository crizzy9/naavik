"""Gmail one-screen connect flow (POST /api/v1/integrations/email/gmail).

Contract: two fields only (address + app password); host/port/TLS/username
derived; pasted app passwords keep Google's spaces; test-before-save;
honest errors; first sync runs immediately after save.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.uses_sample_data_shims

_CSRF = "matching-csrf-token-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


@pytest.fixture()
def client(monkeypatch) -> TestClient:
    from main import app

    return TestClient(app, raise_server_exceptions=True)


def _post(client, **form):
    return client.post(
        "/api/v1/integrations/email/gmail",
        data=form,
        cookies={"naavik_session": "fake-1", "naavik_csrf": _CSRF},
        headers={"X-CSRF-Token": _CSRF},
    )


def test_rejects_malformed_app_password_before_any_network(client, monkeypatch):
    from api import integrations_email as mod

    probe = AsyncMock()
    monkeypatch.setattr(mod.email_sync, "test_imap_connection", probe)
    r = _post(client, account_email="me@gmail.com", app_password="hunter2")
    assert r.status_code == 422
    assert "app" in r.text and "password" in r.text
    probe.assert_not_awaited()


def test_connection_failure_is_honest_and_saves_nothing(client, monkeypatch):
    from api import integrations_email as mod

    monkeypatch.setattr(
        mod.email_sync,
        "test_imap_connection",
        AsyncMock(return_value=(False, "IMAP login failed")),
    )
    saved = AsyncMock()
    monkeypatch.setattr(mod, "_upsert_imap_account", saved)
    r = _post(client, account_email="me@gmail.com", app_password="abcd efgh ijkl mnop")
    assert r.status_code == 422
    assert "IMAP login failed" in r.text
    saved.assert_not_awaited()


def test_success_derives_gmail_settings_and_runs_first_sync(client, monkeypatch):
    from api import integrations_email as mod

    probe = AsyncMock(return_value=(True, None))
    monkeypatch.setattr(mod.email_sync, "test_imap_connection", probe)

    account = SimpleNamespace(id=1, account_email="me@gmail.com")
    upsert = AsyncMock(return_value=account)
    monkeypatch.setattr(mod, "_upsert_imap_account", upsert)

    sync = AsyncMock(return_value=SimpleNamespace(fetched=42, new=7))
    monkeypatch.setattr(mod.email_sync, "sync_account", sync)

    r = _post(client, account_email="me@gmail.com", app_password="abcd efgh ijkl mnop")
    assert r.status_code == 200
    # Spaces stripped from the pasted app password.
    assert probe.await_args.kwargs["password"] == "abcdefghijklmnop"
    assert probe.await_args.kwargs["host"] == "imap.gmail.com"
    assert probe.await_args.kwargs["port"] == 993
    assert probe.await_args.kwargs["username"] == "me@gmail.com"
    # Derived settings persisted.
    assert upsert.await_args.kwargs["imap_host"] == "imap.gmail.com"
    assert upsert.await_args.kwargs["imap_use_tls"] is True
    # First sync ran and its counts surface in the response.
    sync.assert_awaited_once()
    assert "42" in r.text and "7 new" in r.text
    assert "emailConnected" in r.headers.get("HX-Trigger", "")


@pytest.mark.uses_sample_data_shims
def test_integrations_page_leads_with_gmail_card(client):
    r = client.get("/integrations/email", cookies={"naavik_session": "fake-1"})
    assert r.status_code == 200
    assert 'data-testid="gmail-connect-card"' in r.text
    assert "myaccount.google.com/apppasswords" in r.text
    assert 'data-testid="imap-advanced"' in r.text
    # Gmail card comes before the advanced IMAP form.
    assert r.text.index("gmail-connect-card") < r.text.index("imap-advanced")
