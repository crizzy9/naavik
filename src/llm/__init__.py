"""LLM provider factory.

Per BACKEND.md § M.2 + plan 10 § B.4. Resolves the right provider class
from a `Settings` row; API keys come from env vars via pydantic-settings
(`config.settings.anthropic_api_key` / `openai_api_key` / `ollama_base_url`).

Plan 26 (0.2.0.01) deleted the encrypted vault. The factory no longer
reads from `services.vault`; env is the single source of secret material.
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


def get_provider(
    user_settings: Settings,
    *,
    fallback: bool = False,
) -> LLMProvider:
    """Resolve a concrete `LLMProvider` from a user's `Settings` row.

    `fallback=True` returns the configured fallback provider (if set) — used
    by `services/llm_tracker` when the primary errors with 500/timeout.

    API keys come from env vars (`ANTHROPIC_API_KEY` / `OPENAI_API_KEY`);
    the Ollama base URL similarly. Calls still flow through
    `services.llm_tracker.tracked_call` so `ApiUsage` is persisted.
    """
    target = user_settings.llm_fallback_provider if fallback else user_settings.llm_provider
    if target is None:
        raise LLMProviderError("no llm_provider configured", kind="auth_required")

    if target is LLMProviderEnum.ANTHROPIC:
        from .anthropic import AnthropicProvider

        api_key = app_settings.anthropic_api_key or ""
        return AnthropicProvider(api_key=api_key, model=user_settings.llm_model)

    if target is LLMProviderEnum.OPENAI:
        from .openai import OpenAIProvider

        api_key = app_settings.openai_api_key or ""
        return OpenAIProvider(api_key=api_key, model=user_settings.llm_model)

    if target is LLMProviderEnum.OLLAMA:
        from .ollama import OllamaProvider

        return OllamaProvider(
            base_url=app_settings.ollama_base_url,
            model=user_settings.llm_model,
        )

    raise LLMProviderError(f"unsupported llm_provider: {target}", kind="provider_error")


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
