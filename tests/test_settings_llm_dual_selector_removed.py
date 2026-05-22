"""Plan 70 (0.3.3.13): Settings · LLM dual-selector cleanup.

The "Active provider" radio-card section was deleted; the API-key env-presence
card grid is the single canonical surface, with a small env-resolved active-
provider chip in the header.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.uses_sample_data_shims


@pytest.fixture(scope="module")
def client() -> TestClient:
    from main import app

    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture(scope="module")
def auth_cookies() -> dict[str, str]:
    return {"naavik_session": "fake-1"}


def test_settings_llm_tab_active_provider_radio_section_deleted(client: TestClient, auth_cookies):
    """No `<input type="radio" name="llm_provider">` element rendered."""
    r = client.get("/settings/llm-provider", cookies=auth_cookies)
    assert r.status_code == 200
    body = r.text
    # The radio surface from `components/provider_card.html` is gone.
    assert 'name="llm_provider"' not in body
    # The redundant "Active provider" section header is gone too.
    assert "Active provider" not in body


def test_settings_llm_tab_env_presence_cards_still_render(client: TestClient, auth_cookies):
    """The API-key env-presence card grid remains the canonical surface."""
    r = client.get("/settings/llm-provider", cookies=auth_cookies)
    assert r.status_code == 200
    body = r.text
    # Env-indicator cards still surface ANTHROPIC / OPENAI / OLLAMA env vars.
    assert 'data-env-indicator="anthropic"' in body
    assert 'data-env-indicator="openai"' in body
    assert 'data-env-indicator="ollama"' in body
    assert "ANTHROPIC_API_KEY" in body
    assert "OPENAI_API_KEY" in body
    assert "OLLAMA_BASE_URL" in body


def test_settings_llm_tab_renders_env_resolved_active_provider_chip(
    client: TestClient, auth_cookies, monkeypatch
):
    """The new active-provider chip surfaces the env-resolved choice."""
    from config import settings as app_settings

    monkeypatch.setattr(app_settings, "anthropic_api_key", "sk-ant-test")
    monkeypatch.setattr(app_settings, "openai_api_key", None)

    r = client.get("/settings/llm-provider", cookies=auth_cookies)
    assert r.status_code == 200
    body = r.text
    # Chip carries the env-resolved id + visible name.
    assert 'data-active-provider="anthropic"' in body
    # Defensive: should NOT carry the deleted "Active provider" header.
    assert "Active provider</h2>" not in body
