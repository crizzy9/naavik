"""Settings · LLM Provider form-wiring tests.

Plan 26 (0.2.0.01, 2026-05-19): the encrypted vault was deleted; API keys
are configured via env vars. The `/_fragments/settings/llm/api-key-field`
endpoint is gone with its template, and the form no longer accepts an
`api_key` value (422 if posted). Coverage retained:

- `/_fragments/settings/llm/model-options?provider=…` returns the per-provider
  model dropdown.
- The LLM tab renders inside `<form hx-put="/api/v1/settings/llm">` with
  the radio HTMX wiring intact.
- The page surfaces env-presence indicators (`data-env-indicator`).
- `PUT /api/v1/settings/llm` rejects `api_key` payloads with 422.
- `PUT /api/v1/settings/llm` accepts form data carrying only provider /
  model and returns rendered HTML (live-DB round-trip gated via
  NAAVIK_LIVE_DB).
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client() -> TestClient:
    from main import app

    return TestClient(app)


@pytest.fixture(scope="module")
def auth_cookies() -> dict[str, str]:
    return {"naavik_session": "fake-1"}


class _NoopSession:
    """Minimum surface for `Depends(get_session)` — never runs SQL."""

    async def commit(self):  # pragma: no cover
        return None

    async def rollback(self):  # pragma: no cover
        return None

    async def close(self):  # pragma: no cover
        return None


async def _fake_get_session():
    yield _NoopSession()


@pytest.fixture(autouse=True)
def _patch_db_dependencies(monkeypatch):
    """Plan 54 / 0.2.5.03: `/settings/llm-provider` now `Depends(get_session)` to
    drive the daily cost-cap widget. Stub the session + cost-tracker so the
    existing assertions remain DB-free.
    """
    from db.session import get_session
    from main import app
    from services import llm_tracker

    async def _fake_today_cost(session, *, user_id):
        return 0.0

    monkeypatch.setattr(llm_tracker, "today_cost_usd", _fake_today_cost)
    app.dependency_overrides[get_session] = _fake_get_session
    yield
    app.dependency_overrides.pop(get_session, None)


# ── Fragment endpoints — provider-aware swaps ────────────────────────────


@pytest.mark.parametrize(
    ("provider", "must_have", "must_not_have"),
    [
        (
            "anthropic",
            ["claude-3.5-sonnet-20250219", "claude-3.5-haiku-20250219"],
            ["llama3.1", "gpt-4o"],
        ),
        (
            "openai",
            ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
            ["claude-3.5", "llama3.1"],
        ),
        (
            "ollama",
            ["llama3.1:70b", "llama3.1:8b", "qwen2.5:32b"],
            ["claude-3.5", "gpt-4o"],
        ),
    ],
    ids=["anthropic", "openai", "ollama"],
)
def test_model_options_fragment_per_provider(
    client: TestClient, auth_cookies, provider, must_have, must_not_have
):
    r = client.get(
        f"/_fragments/settings/llm/model-options?provider={provider}",
        cookies=auth_cookies,
    )
    assert r.status_code == 200, r.text
    body = r.text
    assert 'id="llm-model"' in body
    for m in must_have:
        assert m in body, f"{provider}: missing {m!r}"
    for m in must_not_have:
        assert m not in body, f"{provider}: leaked {m!r}"


def test_model_options_rejects_unknown_provider(client: TestClient, auth_cookies):
    r = client.get("/_fragments/settings/llm/model-options?provider=ggwp", cookies=auth_cookies)
    assert r.status_code == 400


def test_api_key_field_fragment_endpoint_deleted(client: TestClient, auth_cookies):
    """Plan 26: `/_fragments/settings/llm/api-key-field` is gone (404)."""
    r = client.get(
        "/_fragments/settings/llm/api-key-field?provider=anthropic",
        cookies=auth_cookies,
    )
    assert r.status_code == 404


# ── LLM tab page renders the form-wrap + env indicators ─────────────────


def test_llm_tab_renders_form_wrap(client: TestClient, auth_cookies):
    r = client.get("/settings/llm-provider", cookies=auth_cookies)
    assert r.status_code == 200
    body = r.text
    assert 'hx-put="/api/v1/settings/llm"' in body
    assert 'hx-swap="outerHTML"' in body
    # Plan 70 (0.3.3.13): "Active provider" radio surface deleted; the
    # `/_fragments/settings/llm/model-options?provider=...` fragment is
    # no longer wired via radio change. Endpoint remains usable; the LLM
    # tab itself just doesn't trigger it on render.
    assert 'name="llm_provider"' not in body
    # Model dropdown swap target survives.
    assert 'id="llm-model-container"' in body
    # Old api-key container is GONE.
    assert 'id="llm-api-key-container"' not in body
    # No API-key input field renders.
    assert 'name="api_key"' not in body
    assert 'name="ollama_base_url"' not in body
    # New env-presence indicators present.
    assert 'data-env-indicator="anthropic"' in body
    assert 'data-env-indicator="openai"' in body
    assert 'data-env-indicator="ollama"' in body
    # The dead `?create=1` link from plan 10 lives on the login page; ensure
    # we didn't accidentally bring it into Settings.
    assert "?create=1" not in body


# ── PUT rejects secret-carrying payloads ─────────────────────────────────


def test_put_llm_rejects_api_key_in_json_body(client: TestClient, auth_cookies):
    r = client.put(
        "/api/v1/settings/llm",
        json={"api_key": "sk-ant-test"},
        cookies=auth_cookies,
    )
    assert r.status_code == 422
    body = r.json()
    detail = body.get("detail", "")
    assert "env" in detail.lower()
    assert ".env" in detail


def test_put_llm_rejects_ollama_base_url_in_json_body(client: TestClient, auth_cookies):
    r = client.put(
        "/api/v1/settings/llm",
        json={"ollama_base_url": "http://other:11434"},
        cookies=auth_cookies,
    )
    assert r.status_code == 422


def test_put_notifications_rejects_discord_webhook_url(client: TestClient, auth_cookies):
    r = client.put(
        "/api/v1/settings/notifications",
        json={"discord_webhook_url": "https://discord/x"},
        cookies=auth_cookies,
    )
    assert r.status_code == 422


def test_put_notifications_rejects_telegram_bot_token(client: TestClient, auth_cookies):
    r = client.put(
        "/api/v1/settings/notifications",
        json={"telegram_bot_token": "123:ABC"},
        cookies=auth_cookies,
    )
    assert r.status_code == 422


def test_put_notifications_rejects_telegram_chat_id(client: TestClient, auth_cookies):
    r = client.put(
        "/api/v1/settings/notifications",
        json={"telegram_chat_id": "987654321"},
        cookies=auth_cookies,
    )
    assert r.status_code == 422
    body = r.json()
    detail = body.get("detail", "")
    assert "TELEGRAM_CHAT_ID" in detail
    assert ".env" in detail


# ── Live-DB round-trip (opt-in) ──────────────────────────────────────────


_LIVE = os.environ.get("NAAVIK_LIVE_DB", "").strip().lower() in {"1", "true", "yes"}


@pytest.mark.skipif(
    not _LIVE,
    reason="set NAAVIK_LIVE_DB=1 (and DATABASE_URL) to run live-DB form round-trip",
)
def test_put_llm_form_round_trip_persists_provider(client: TestClient, auth_cookies):
    """PUT /api/v1/settings/llm via form data -> returns HTML, persists provider."""
    r = client.put(
        "/api/v1/settings/llm",
        data={"llm_provider": "ollama", "llm_model": "llama3.1:8b"},
        cookies=auth_cookies,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200
    # HTMX path returns rendered HTML, not JSON
    assert "<form" in r.text
    assert "hx-put=" in r.text

    # Confirm the change persisted via the JSON GET
    r2 = client.get("/api/v1/settings/llm", cookies=auth_cookies)
    assert r2.status_code == 200
    body = r2.json()
    assert body["llm_provider"] == "ollama"
    assert body["llm_model"] == "llama3.1:8b"
    assert "env_indicators" in body
    assert set(body["env_indicators"].keys()) == {"anthropic", "openai", "ollama"}
    # Make sure the old fingerprint key doesn't leak back in.
    assert "llm_api_key_fingerprint" not in body

    # Reset for hygiene
    client.put(
        "/api/v1/settings/llm",
        data={
            "llm_provider": "anthropic",
            "llm_model": "claude-3.5-sonnet-20250219",
        },
        cookies=auth_cookies,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
