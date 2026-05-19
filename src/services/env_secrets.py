"""Env-presence indicators — post-vault replacement for `Settings.*_configured`.

Per ROADMAP row 0.2.0.01 (plan 26): the 5 `Settings._configured` boolean
columns + `Settings.llm_api_key_fingerprint` are dropped. Settings UI +
API surfaces still need to render "Anthropic: configured via env ✓ / ✗"
indicators without exposing values.

Each helper reads `config.settings` (pydantic-settings already loads from
`.env` + actual env). Empty / None means absent; non-empty means present.
NEVER returns the value itself; the caller cannot leak.
"""

from __future__ import annotations

from config import settings as app_settings
from models.enums import LLMProvider


def llm_provider_configured(provider: LLMProvider) -> bool:
    """True iff an API key is set in env for the given provider.

    Ollama returns True iff `OLLAMA_BASE_URL` is non-empty (default
    `http://localhost:11434` is always set, so effectively always True —
    the indicator follows the same shape as Anthropic/OpenAI for UI uniformity).
    """
    if provider is LLMProvider.ANTHROPIC:
        return bool(app_settings.anthropic_api_key)
    if provider is LLMProvider.OPENAI:
        return bool(app_settings.openai_api_key)
    if provider is LLMProvider.OLLAMA:
        return bool(app_settings.ollama_base_url)
    return False


def discord_webhook_configured() -> bool:
    return bool(app_settings.discord_webhook_url)


def telegram_bot_configured() -> bool:
    return bool(app_settings.telegram_bot_token) and bool(app_settings.telegram_chat_id)


def portfolio_webhook_configured() -> bool:
    return bool(app_settings.portfolio_webhook_url)


def env_indicators_for_llm_tab() -> dict[str, bool]:
    """Bundle for `_settings_llm.html` template context."""
    return {
        "anthropic": llm_provider_configured(LLMProvider.ANTHROPIC),
        "openai": llm_provider_configured(LLMProvider.OPENAI),
        "ollama": llm_provider_configured(LLMProvider.OLLAMA),
    }


def env_indicators_for_notifications_tab() -> dict[str, bool]:
    return {
        "discord": discord_webhook_configured(),
        "telegram": telegram_bot_configured(),
        "portfolio": portfolio_webhook_configured(),
    }


def is_configured(scope: str) -> bool:
    """Generic scope-based lookup.

    Accepts any of the canonical UI / API scope names: `anthropic`,
    `openai`, `ollama`, `discord`, `telegram`, `portfolio`. Returns False
    on unknown scope (caller-facing typo guard).
    """
    if scope == "anthropic":
        return llm_provider_configured(LLMProvider.ANTHROPIC)
    if scope == "openai":
        return llm_provider_configured(LLMProvider.OPENAI)
    if scope == "ollama":
        return llm_provider_configured(LLMProvider.OLLAMA)
    if scope == "discord":
        return discord_webhook_configured()
    if scope == "telegram":
        return telegram_bot_configured()
    if scope == "portfolio":
        return portfolio_webhook_configured()
    return False
