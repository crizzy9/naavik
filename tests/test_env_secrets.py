"""Env-secrets indicator tests.

Plan 26 (0.2.0.01): `services/env_secrets.py` replaces the vault-derived
`Settings._configured` booleans + `Settings.llm_api_key_fingerprint`
column. Indicator helpers read from `config.settings` (pydantic-settings)
and return bools without surfacing values.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def env_settings(monkeypatch):
    """Reset every env-derived setting to a clean known state."""
    from config import settings as app_settings

    monkeypatch.setattr(app_settings, "anthropic_api_key", None)
    monkeypatch.setattr(app_settings, "openai_api_key", None)
    monkeypatch.setattr(app_settings, "ollama_base_url", "http://localhost:11434")
    monkeypatch.setattr(app_settings, "discord_webhook_url", None)
    monkeypatch.setattr(app_settings, "telegram_bot_token", None)
    monkeypatch.setattr(app_settings, "telegram_chat_id", None)
    monkeypatch.setattr(app_settings, "portfolio_webhook_url", None)
    return app_settings


def test_llm_provider_configured_anthropic_absent(env_settings):
    from models import LLMProvider
    from services import env_secrets

    assert env_secrets.llm_provider_configured(LLMProvider.ANTHROPIC) is False


def test_llm_provider_configured_anthropic_present(env_settings, monkeypatch):
    from models import LLMProvider
    from services import env_secrets

    monkeypatch.setattr(env_settings, "anthropic_api_key", "sk-ant-test-redacted")
    assert env_secrets.llm_provider_configured(LLMProvider.ANTHROPIC) is True


def test_llm_provider_configured_openai_present(env_settings, monkeypatch):
    from models import LLMProvider
    from services import env_secrets

    monkeypatch.setattr(env_settings, "openai_api_key", "sk-openai-test-redacted")
    assert env_secrets.llm_provider_configured(LLMProvider.OPENAI) is True


def test_llm_provider_configured_ollama_always_true_when_base_url_set(env_settings):
    from models import LLMProvider
    from services import env_secrets

    # Default `http://localhost:11434` set in the fixture; Ollama always
    # has a base URL, so the indicator is always True.
    assert env_secrets.llm_provider_configured(LLMProvider.OLLAMA) is True


def test_discord_webhook_configured_toggles_with_env(env_settings, monkeypatch):
    from services import env_secrets

    assert env_secrets.discord_webhook_configured() is False
    monkeypatch.setattr(env_settings, "discord_webhook_url", "https://discord/x")
    assert env_secrets.discord_webhook_configured() is True


def test_telegram_bot_configured_requires_both_token_and_chat_id(env_settings, monkeypatch):
    from services import env_secrets

    assert env_secrets.telegram_bot_configured() is False
    monkeypatch.setattr(env_settings, "telegram_bot_token", "123:ABC")
    assert env_secrets.telegram_bot_configured() is False
    monkeypatch.setattr(env_settings, "telegram_chat_id", "987654321")
    assert env_secrets.telegram_bot_configured() is True


def test_portfolio_webhook_configured(env_settings, monkeypatch):
    from services import env_secrets

    assert env_secrets.portfolio_webhook_configured() is False
    monkeypatch.setattr(env_settings, "portfolio_webhook_url", "https://api.netlify.com/build/x")
    assert env_secrets.portfolio_webhook_configured() is True


def test_env_indicators_for_llm_tab_returns_three_keys(env_settings):
    from services import env_secrets

    bundle = env_secrets.env_indicators_for_llm_tab()
    assert set(bundle.keys()) == {"anthropic", "openai", "ollama"}
    assert bundle["anthropic"] is False
    assert bundle["openai"] is False
    assert bundle["ollama"] is True


def test_env_indicators_for_notifications_tab_returns_three_keys(env_settings):
    from services import env_secrets

    bundle = env_secrets.env_indicators_for_notifications_tab()
    assert set(bundle.keys()) == {"discord", "telegram", "portfolio"}
    assert bundle["discord"] is False
    assert bundle["telegram"] is False
    assert bundle["portfolio"] is False


def test_is_configured_dispatches_by_scope(env_settings, monkeypatch):
    from services import env_secrets

    monkeypatch.setattr(env_settings, "anthropic_api_key", "sk-x")
    monkeypatch.setattr(env_settings, "discord_webhook_url", "https://discord/x")

    assert env_secrets.is_configured("anthropic") is True
    assert env_secrets.is_configured("openai") is False
    assert env_secrets.is_configured("discord") is True
    assert env_secrets.is_configured("telegram") is False
    assert env_secrets.is_configured("portfolio") is False
    assert env_secrets.is_configured("ollama") is True


def test_is_configured_unknown_scope_returns_false(env_settings):
    from services import env_secrets

    assert env_secrets.is_configured("nonsense") is False
    assert env_secrets.is_configured("") is False


def test_scraper_source_configured_workday_reads_settings(env_settings):
    """Workday source is configured iff Settings.workday_companies is non-empty."""
    from types import SimpleNamespace

    from models import JobSource
    from services import env_secrets

    empty = SimpleNamespace(workday_companies=[], linkedin_keywords=None, indeed_keywords=None)
    assert env_secrets.scraper_source_configured(JobSource.WORKDAY, empty) is False

    populated = SimpleNamespace(
        workday_companies=["adobe", "salesforce"],
        linkedin_keywords=None,
        indeed_keywords=None,
    )
    assert env_secrets.scraper_source_configured(JobSource.WORKDAY, populated) is True


def test_scraper_source_configured_greenhouse_lever_ashby_read_env(env_settings, monkeypatch):
    """Company-list env vars drive Greenhouse / Lever / Ashby configured indicator."""
    from types import SimpleNamespace

    from models import JobSource
    from services import env_secrets

    settings = SimpleNamespace(workday_companies=[], linkedin_keywords=None, indeed_keywords=None)

    monkeypatch.setattr(env_settings, "greenhouse_companies", None)
    monkeypatch.setattr(env_settings, "lever_companies", None)
    monkeypatch.setattr(env_settings, "ashby_companies", None)
    assert env_secrets.scraper_source_configured(JobSource.GREENHOUSE, settings) is False
    assert env_secrets.scraper_source_configured(JobSource.LEVER, settings) is False
    assert env_secrets.scraper_source_configured(JobSource.ASHBY, settings) is False

    monkeypatch.setattr(env_settings, "greenhouse_companies", ["anthropic"])
    monkeypatch.setattr(env_settings, "lever_companies", ["netflix"])
    monkeypatch.setattr(env_settings, "ashby_companies", ["ramp"])
    assert env_secrets.scraper_source_configured(JobSource.GREENHOUSE, settings) is True
    assert env_secrets.scraper_source_configured(JobSource.LEVER, settings) is True
    assert env_secrets.scraper_source_configured(JobSource.ASHBY, settings) is True


def test_scraper_source_configured_linkedin_indeed_read_keywords(env_settings):
    """LinkedIn / Indeed configured indicator follows per-user keywords."""
    from types import SimpleNamespace

    from models import JobSource
    from services import env_secrets

    empty = SimpleNamespace(workday_companies=[], linkedin_keywords=None, indeed_keywords=None)
    assert env_secrets.scraper_source_configured(JobSource.LINKEDIN, empty) is False
    assert env_secrets.scraper_source_configured(JobSource.INDEED, empty) is False

    populated = SimpleNamespace(
        workday_companies=[],
        linkedin_keywords=["staff engineer"],
        indeed_keywords=["sre"],
    )
    assert env_secrets.scraper_source_configured(JobSource.LINKEDIN, populated) is True
    assert env_secrets.scraper_source_configured(JobSource.INDEED, populated) is True


def test_scraper_source_configured_unsupported_sources_return_false(env_settings):
    """COMPANY_DIRECT / RSSHUB / N8N_LEGACY / MANUAL are not surfaced on the panel."""
    from types import SimpleNamespace

    from models import JobSource
    from services import env_secrets

    settings = SimpleNamespace(
        workday_companies=["x"], linkedin_keywords=["x"], indeed_keywords=["x"]
    )
    assert env_secrets.scraper_source_configured(JobSource.COMPANY_DIRECT, settings) is False
    assert env_secrets.scraper_source_configured(JobSource.RSSHUB, settings) is False
    assert env_secrets.scraper_source_configured(JobSource.N8N_LEGACY, settings) is False
    assert env_secrets.scraper_source_configured(JobSource.MANUAL, settings) is False


def test_helpers_never_return_secret_values(env_settings, monkeypatch):
    """Defensive: every indicator helper returns bool, never the actual value."""
    from services import env_secrets

    monkeypatch.setattr(env_settings, "anthropic_api_key", "sk-ant-DO-NOT-LEAK")
    monkeypatch.setattr(env_settings, "discord_webhook_url", "https://discord/SECRET")

    from models import LLMProvider

    val = env_secrets.llm_provider_configured(LLMProvider.ANTHROPIC)
    assert isinstance(val, bool)
    assert val is True

    val2 = env_secrets.discord_webhook_configured()
    assert isinstance(val2, bool)
    assert val2 is True

    bundle = env_secrets.env_indicators_for_llm_tab()
    for v in bundle.values():
        assert isinstance(v, bool)
