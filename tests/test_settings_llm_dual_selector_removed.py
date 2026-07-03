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
    # (Item 10 reintroduced `llm_provider` as a HIDDEN field so saving a
    # model aligns the stored provider — only the radio stays banned.)
    assert 'type="radio" name="llm_provider"' not in body
    assert '<input type="hidden" name="llm_provider"' in body
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


# ── 0.7.0.48 fold-in: env-var workflow clarifications ───────────────────


def test_settings_llm_tab_renders_howto_instructional_block(client: TestClient, auth_cookies):
    """The "How LLM providers work" block always renders + names the env vars."""
    r = client.get("/settings/llm-provider", cookies=auth_cookies)
    assert r.status_code == 200
    body = r.text
    assert "data-llm-howto" in body
    assert "How LLM providers work" in body
    # Names the canonical env-var workflow.
    assert "ANTHROPIC_API_KEY" in body
    assert "OPENAI_API_KEY" in body
    assert "OLLAMA_BASE_URL" in body
    assert "restart" in body.lower()


def test_settings_llm_tab_renders_unconfigured_warning_when_no_env_keys(
    client: TestClient, auth_cookies, monkeypatch
):
    """No provider env-configured → prominent amber `data-llm-warning="unconfigured"` banner."""
    from config import settings as app_settings

    monkeypatch.setattr(app_settings, "anthropic_api_key", None)
    monkeypatch.setattr(app_settings, "openai_api_key", None)
    monkeypatch.setattr(app_settings, "ollama_base_url", None)

    r = client.get("/settings/llm-provider", cookies=auth_cookies)
    assert r.status_code == 200
    body = r.text
    assert 'data-llm-warning="unconfigured"' in body
    assert "No LLM provider configured" in body
    # Mismatch banner must NOT also fire (mutually exclusive).
    assert 'data-llm-warning="mismatch"' not in body


def test_settings_llm_tab_renders_mismatch_warning_when_pref_lacks_env(
    client: TestClient, auth_cookies, monkeypatch
):
    """Saved pref = ANTHROPIC, only OPENAI_API_KEY set → mismatch banner.

    Models for the active (env-resolved) provider populate the dropdown so the
    operator sees the catalog for the provider LLM calls will actually use.
    """
    from config import settings as app_settings

    # `Settings.llm_provider` defaults to ANTHROPIC for the sample-data user.
    monkeypatch.setattr(app_settings, "anthropic_api_key", None)
    monkeypatch.setattr(app_settings, "openai_api_key", "sk-openai-mismatch")

    r = client.get("/settings/llm-provider", cookies=auth_cookies)
    assert r.status_code == 200
    body = r.text
    assert 'data-llm-warning="mismatch"' in body
    assert 'data-active-provider="openai"' in body
    # The mismatch section carries pref-vs-active attributes.
    assert 'data-pref-provider="anthropic"' in body
    # Model dropdown follows env-resolved provider (OpenAI models, not Claude).
    assert "gpt-4o" in body
    # Unconfigured banner must NOT also fire.
    assert 'data-llm-warning="unconfigured"' not in body


def test_settings_llm_tab_active_chip_when_pref_matches_env(
    client: TestClient, auth_cookies, monkeypatch
):
    """Saved pref = ANTHROPIC + `ANTHROPIC_API_KEY` set → no warning banner."""
    from config import settings as app_settings

    monkeypatch.setattr(app_settings, "anthropic_api_key", "sk-ant-match")
    monkeypatch.setattr(app_settings, "openai_api_key", None)

    r = client.get("/settings/llm-provider", cookies=auth_cookies)
    assert r.status_code == 200
    body = r.text
    assert 'data-llm-warning="mismatch"' not in body
    assert 'data-llm-warning="unconfigured"' not in body
    # Active-provider env card carries `data-is-active="true"`.
    assert 'data-env-indicator="anthropic"\n               data-configured="true"' in body or (
        'data-env-indicator="anthropic"' in body and 'data-is-active="true"' in body
    )
