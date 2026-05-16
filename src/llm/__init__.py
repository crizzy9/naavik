"""LLM provider factory.

Per BACKEND.md § M.2 + plan 10 § B.4. Resolves the right provider class
from a `Settings` row; pulls API keys from the encrypted vault; never
reads keys from `Settings` directly.
"""

from __future__ import annotations

from config import settings as app_settings
from models import LLMProvider as LLMProviderEnum
from models import Settings
from services import vault as vault_svc

from .base import (
    CompletionResult,
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

    API keys are resolved via the vault — never from `Settings` directly.
    Key for scope `"llm"` is keyed by provider id (`"anthropic"`, `"openai"`).
    """
    target = user_settings.llm_fallback_provider if fallback else user_settings.llm_provider
    if target is None:
        raise LLMProviderError("no llm_provider configured", kind="auth_required")

    if target is LLMProviderEnum.ANTHROPIC:
        from .anthropic import AnthropicProvider

        api_key = (
            vault_svc.get("llm", "anthropic", caller="llm.factory")
            or app_settings.anthropic_api_key
        )
        return AnthropicProvider(api_key=api_key or "", model=user_settings.llm_model)

    if target is LLMProviderEnum.OPENAI:
        from .openai import OpenAIProvider

        api_key = (
            vault_svc.get("llm", "openai", caller="llm.factory") or app_settings.openai_api_key
        )
        return OpenAIProvider(api_key=api_key or "", model=user_settings.llm_model)

    if target is LLMProviderEnum.OLLAMA:
        from .ollama import OllamaProvider

        return OllamaProvider(
            base_url=app_settings.ollama_base_url,
            model=user_settings.llm_model,
        )

    raise LLMProviderError(f"unsupported llm_provider: {target}", kind="provider_error")


__all__ = [
    "CompletionResult",
    "LLMProvider",
    "LLMProviderError",
    "StructuredResult",
    "get_provider",
]
