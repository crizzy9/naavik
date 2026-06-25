"""LLM provider factory.

Per BACKEND.md § M.2 + plan 10 § B.4. Resolves the right provider class
from a `Settings` row; API keys come from env vars via pydantic-settings
(`config.settings.anthropic_api_key` / `openai_api_key` / `ollama_base_url`).

Plan 26 (0.2.0.01) deleted the encrypted vault. The factory no longer
reads from `services.vault`; env is the single source of secret material.

0.7.0.48 fold-in: `get_provider` now honors env-presence — if the user's
preferred `Settings.llm_provider` has no env key set, the factory falls
back to whichever provider IS env-configured (precedence
ANTHROPIC > OPENAI > OLLAMA via `env_secrets.resolve_active_llm_provider`).
The DB-stored `llm_provider` defaults to ANTHROPIC, so a fresh user with
only `OPENAI_API_KEY` set used to hit silent `auth_required` on every
LLM call — chip said "Active: OpenAI" but the factory built an Anthropic
provider with `api_key=""`. Env now wins; the DB column tracks the user's
*preference* + drives the model dropdown's provider-grouping.
"""

from __future__ import annotations

from config import settings as app_settings
from models import LLMProvider as LLMProviderEnum
from models import Settings

from .base import (
    CompletionResult,
    EmbeddingResult,
    LLMProvider,
    LLMProviderError,
    StructuredResult,
)


def _provider_has_env_key(provider: LLMProviderEnum) -> bool:
    """True iff the requested provider has its env key set."""
    if provider is LLMProviderEnum.ANTHROPIC:
        return bool(app_settings.anthropic_api_key)
    if provider is LLMProviderEnum.OPENAI:
        return bool(app_settings.openai_api_key)
    if provider is LLMProviderEnum.OLLAMA:
        return bool(app_settings.ollama_base_url)
    return False


def _build_provider(target: LLMProviderEnum, model: str | None) -> LLMProvider:
    """Construct the concrete provider; assumes caller verified env key."""
    if target is LLMProviderEnum.ANTHROPIC:
        from .anthropic import AnthropicProvider

        return AnthropicProvider(api_key=app_settings.anthropic_api_key or "", model=model)

    if target is LLMProviderEnum.OPENAI:
        from .openai import OpenAIProvider

        return OpenAIProvider(api_key=app_settings.openai_api_key or "", model=model)

    if target is LLMProviderEnum.OLLAMA:
        from .ollama import OllamaProvider

        return OllamaProvider(base_url=app_settings.ollama_base_url, model=model)

    raise LLMProviderError(f"unsupported llm_provider: {target}", kind="provider_error")


def get_provider(
    user_settings: Settings,
    *,
    fallback: bool = False,
) -> LLMProvider:
    """Resolve a concrete `LLMProvider` from a user's `Settings` row.

    `fallback=True` returns the configured fallback provider (if set) — used
    by `services/llm_tracker` when the primary errors with 500/timeout.

    Resolution order:
      1. Honor `Settings.llm_(fallback_)provider` IFF its env key is set.
      2. Fall back to env-resolved active provider per
         `env_secrets.resolve_active_llm_provider` (ANTHROPIC > OPENAI > OLLAMA).
      3. If nothing is configured anywhere, raise `auth_required`.

    Calls still flow through `services.llm_tracker.tracked_call` so
    `ApiUsage` is persisted.
    """
    target = user_settings.llm_fallback_provider if fallback else user_settings.llm_provider
    if target is not None and _provider_has_env_key(target):
        return _build_provider(target, user_settings.llm_model)

    # Preferred provider lacks env key — fall back to whichever provider IS
    # env-configured. Avoids the silent "auth_required" path operators hit
    # when `OPENAI_API_KEY` is set but `Settings.llm_provider` defaulted to
    # ANTHROPIC.
    from services.env_secrets import resolve_active_llm_provider

    active_id = resolve_active_llm_provider()
    if active_id is None:
        raise LLMProviderError(
            "no LLM provider configured — set ANTHROPIC_API_KEY, OPENAI_API_KEY, "
            "or OLLAMA_BASE_URL in .env and restart",
            kind="auth_required",
        )

    active_enum = LLMProviderEnum(active_id)
    return _build_provider(active_enum, user_settings.llm_model)


def get_embedding_provider(
    user_settings: Settings,
) -> LLMProvider | None:
    """Resolve a per-user embedding provider from `Settings.embedding_provider`.

    Plan 61 / 0.2.7.16. Returns None when not configured (toggle OFF, no
    selection, or selected provider has no env-presence). Caller treats
    None as "feature disabled" — no-op.

    Resolution order:
      1. Honor explicit `settings.embedding_provider` ("openai" | "ollama").
      2. Default fallback: ollama if `OLLAMA_BASE_URL` set; openai if
         `OPENAI_API_KEY` set; otherwise None.

    Anthropic is rejected — it does not offer embeddings.
    """
    if not user_settings.semantic_match_enabled:
        return None

    selected = (user_settings.embedding_provider or "").lower() or None
    if selected == "anthropic":
        return None

    if selected == "openai":
        if not app_settings.openai_api_key:
            return None
        from .openai import OpenAIProvider

        return OpenAIProvider(
            api_key=app_settings.openai_api_key,
            model=user_settings.llm_model,
        )

    if selected == "ollama":
        from .ollama import OllamaProvider

        return OllamaProvider(
            base_url=app_settings.ollama_base_url,
            model=user_settings.llm_model,
        )

    # No selection — fall back to env presence.
    if app_settings.ollama_base_url:
        from .ollama import OllamaProvider

        return OllamaProvider(
            base_url=app_settings.ollama_base_url,
            model=user_settings.llm_model,
        )
    if app_settings.openai_api_key:
        from .openai import OpenAIProvider

        return OpenAIProvider(
            api_key=app_settings.openai_api_key,
            model=user_settings.llm_model,
        )
    return None


__all__ = [
    "CompletionResult",
    "EmbeddingResult",
    "LLMProvider",
    "LLMProviderError",
    "StructuredResult",
    "get_embedding_provider",
    "get_provider",
]
