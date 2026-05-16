"""Settings · LLM Provider form-wiring tests — plan 10b (item 6, 2026-05-03).

Coverage:
- `GET /_fragments/settings/llm/model-options?provider=…` returns the per-provider
  model `<select>` options.
- `GET /_fragments/settings/llm/api-key-field?provider=…` returns the per-provider
  api-key (or Ollama base URL) field.
- The LLM tab template renders inside a `<form hx-put="/api/v1/settings/llm">`
  with the radio HTMX wiring intact (no dead `?create=1` link, no hardcoded
  Claude-only model list).
- `PUT /api/v1/settings/llm` accepts form data and returns rendered HTML
  (the live-DB round-trip is gated via NAAVIK_LIVE_DB).
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


def test_api_key_field_anthropic_shows_password_input(client: TestClient, auth_cookies):
    r = client.get(
        "/_fragments/settings/llm/api-key-field?provider=anthropic",
        cookies=auth_cookies,
    )
    assert r.status_code == 200
    body = r.text
    assert 'id="llm-api-key"' in body
    assert 'placeholder="sk-ant-…"' in body
    # Anthropic does NOT show the Ollama base URL field
    assert "OLLAMA BASE URL" not in body
    assert "ollama_base_url" not in body


def test_api_key_field_openai_shows_password_input(client: TestClient, auth_cookies):
    r = client.get(
        "/_fragments/settings/llm/api-key-field?provider=openai",
        cookies=auth_cookies,
    )
    assert r.status_code == 200
    body = r.text
    assert 'id="llm-api-key"' in body
    assert 'placeholder="sk-…"' in body
    assert "OLLAMA BASE URL" not in body


def test_api_key_field_ollama_swaps_to_base_url_input(client: TestClient, auth_cookies):
    """Ollama is local — show OLLAMA_BASE_URL input, hide the API key field."""
    r = client.get(
        "/_fragments/settings/llm/api-key-field?provider=ollama",
        cookies=auth_cookies,
    )
    assert r.status_code == 200
    body = r.text
    assert "OLLAMA BASE URL" in body
    assert 'name="ollama_base_url"' in body
    assert "Local provider" in body
    assert "no API key required" in body
    # The visible password input must NOT be present.
    assert 'id="llm-api-key"' not in body
    # And the form keeps an api_key=<empty> hidden input so the PUT handler
    # treats it as "no change" rather than "field missing".
    assert 'name="api_key"' in body
    assert 'type="hidden"' in body


def test_api_key_field_rejects_unknown_provider(client: TestClient, auth_cookies):
    r = client.get(
        "/_fragments/settings/llm/api-key-field?provider=hax",
        cookies=auth_cookies,
    )
    assert r.status_code == 400


# ── LLM tab page renders the form-wrap + radio HTMX wiring ───────────────


def test_llm_tab_renders_form_wrap(client: TestClient, auth_cookies):
    r = client.get("/settings/llm-provider", cookies=auth_cookies)
    assert r.status_code == 200
    body = r.text
    assert 'hx-put="/api/v1/settings/llm"' in body
    assert 'hx-swap="outerHTML"' in body
    # Provider radios carry the model-options swap target
    assert "/_fragments/settings/llm/model-options?provider=anthropic" in body
    assert "/_fragments/settings/llm/model-options?provider=openai" in body
    assert "/_fragments/settings/llm/model-options?provider=ollama" in body
    # Containers used as swap targets exist
    assert 'id="llm-model-container"' in body
    assert 'id="llm-api-key-container"' in body
    # The dead `?create=1` link from plan 10 lives on the login page; ensure
    # we didn't accidentally bring it into Settings.
    assert "?create=1" not in body


# ── Live-DB round-trip (opt-in) ──────────────────────────────────────────


_LIVE = os.environ.get("NAAVIK_LIVE_DB", "").strip().lower() in {"1", "true", "yes"}


@pytest.mark.skipif(
    not _LIVE,
    reason="set NAAVIK_LIVE_DB=1 (and DATABASE_URL) to run live-DB form round-trip",
)
def test_put_llm_form_round_trip_persists_provider(client: TestClient, auth_cookies):
    """PUT /api/v1/settings/llm via form data → returns HTML, persists provider."""
    r = client.put(
        "/api/v1/settings/llm",
        data={"llm_provider": "ollama", "llm_model": "llama3.1:8b", "api_key": ""},
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

    # Reset for hygiene
    client.put(
        "/api/v1/settings/llm",
        data={
            "llm_provider": "anthropic",
            "llm_model": "claude-3.5-sonnet-20250219",
            "api_key": "",
        },
        cookies=auth_cookies,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
