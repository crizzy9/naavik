"""Live provider model catalogs with a cached fallback (P6.4).

The Settings · LLM Provider model dropdown used to be a hardcoded list
that aged badly (gpt-4o-era entries only). `list_models(provider_id)`
now asks each provider's list-models API at request time — new models
appear without code changes — with a 10-minute in-process cache and a
conservative static fallback when the API is unreachable or no key is
configured.
"""

from __future__ import annotations

import logging
import time

import httpx

from config import settings as app_settings

log = logging.getLogger(__name__)

_TTL_SECONDS = 600
_HTTP_TIMEOUT = 5.0

# Conservative fallback when the provider API is unreachable / unkeyed.
FALLBACK_MODELS: dict[str, list[str]] = {
    "anthropic": [
        "claude-opus-4-8",
        "claude-sonnet-4-6",
        "claude-haiku-4-5",
    ],
    "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
    "ollama": ["llama3.1:70b", "llama3.1:8b", "qwen2.5:32b"],
}

# Non-chat OpenAI artifacts that must not land in a chat-model dropdown.
_OPENAI_EXCLUDE_TOKENS = (
    "embedding",
    "whisper",
    "tts",
    "dall-e",
    "moderation",
    "audio",
    "realtime",
    "transcribe",
    "image",
    "davinci",
    "babbage",
)

_cache: dict[str, tuple[float, list[str]]] = {}


async def _fetch_anthropic() -> list[str]:
    if not app_settings.anthropic_api_key:
        return []
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        r = await client.get(
            "https://api.anthropic.com/v1/models",
            headers={
                "x-api-key": app_settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
            },
            params={"limit": 100},
        )
        r.raise_for_status()
        data = r.json().get("data", [])
    return [m["id"] for m in data if isinstance(m, dict) and m.get("id")]


async def _fetch_openai() -> list[str]:
    if not app_settings.openai_api_key:
        return []
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        r = await client.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {app_settings.openai_api_key}"},
        )
        r.raise_for_status()
        data = r.json().get("data", [])
    models = [
        m
        for m in data
        if isinstance(m, dict)
        and m.get("id")
        and (m["id"].startswith("gpt-") or m["id"].startswith("o"))
        and not any(tok in m["id"] for tok in _OPENAI_EXCLUDE_TOKENS)
    ]
    models.sort(key=lambda m: m.get("created", 0), reverse=True)
    return [m["id"] for m in models]


async def _fetch_ollama() -> list[str]:
    if not app_settings.ollama_base_url:
        return []
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        r = await client.get(f"{app_settings.ollama_base_url.rstrip('/')}/api/tags")
        r.raise_for_status()
        data = r.json().get("models", [])
    return [m["name"] for m in data if isinstance(m, dict) and m.get("name")]


_FETCHERS = {
    "anthropic": _fetch_anthropic,
    "openai": _fetch_openai,
    "ollama": _fetch_ollama,
}


async def list_models(provider_id: str) -> list[str]:
    """Current model ids for a provider — live API, TTL cache, static fallback."""
    fetcher = _FETCHERS.get(provider_id)
    if fetcher is None:
        return []

    now = time.monotonic()
    cached = _cache.get(provider_id)
    if cached is not None and now - cached[0] < _TTL_SECONDS:
        return list(cached[1])

    try:
        models = await fetcher()
    except Exception as exc:  # noqa: BLE001 — degrade to cache/fallback
        log.info("model list fetch failed for %s: %s", provider_id, exc)
        models = []

    if models:
        _cache[provider_id] = (now, models)
        return list(models)
    if cached is not None:
        return list(cached[1])  # stale cache beats static fallback
    return list(FALLBACK_MODELS.get(provider_id, []))


def clear_cache() -> None:
    """Test hook."""
    _cache.clear()
