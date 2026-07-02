"""P6.4 — live provider model catalogs with cached fallback (services/llm_models)."""

from __future__ import annotations

import pytest

from services import llm_models


@pytest.fixture(autouse=True)
def _fresh_cache():
    llm_models.clear_cache()
    yield
    llm_models.clear_cache()


@pytest.mark.asyncio
async def test_falls_back_to_static_catalog_when_fetch_fails(monkeypatch):
    async def _boom():
        raise RuntimeError("api down")

    monkeypatch.setitem(llm_models._FETCHERS, "anthropic", _boom)
    models = await llm_models.list_models("anthropic")
    assert models == llm_models.FALLBACK_MODELS["anthropic"]


@pytest.mark.asyncio
async def test_live_fetch_wins_and_is_cached(monkeypatch):
    calls = {"n": 0}

    async def _fetch():
        calls["n"] += 1
        return ["claude-fable-5", "claude-opus-4-8"]

    monkeypatch.setitem(llm_models._FETCHERS, "anthropic", _fetch)
    first = await llm_models.list_models("anthropic")
    second = await llm_models.list_models("anthropic")
    assert first == second == ["claude-fable-5", "claude-opus-4-8"]
    assert calls["n"] == 1  # second call served from cache


@pytest.mark.asyncio
async def test_stale_cache_beats_static_fallback(monkeypatch):
    healthy = {"up": True}

    async def _flaky():
        if not healthy["up"]:
            raise RuntimeError("api down")
        return ["m-live"]

    monkeypatch.setitem(llm_models._FETCHERS, "openai", _flaky)
    monkeypatch.setattr(llm_models, "_TTL_SECONDS", 0)  # force re-fetch each call
    assert await llm_models.list_models("openai") == ["m-live"]
    healthy["up"] = False
    assert await llm_models.list_models("openai") == ["m-live"]  # stale cache


@pytest.mark.asyncio
async def test_unknown_provider_returns_empty():
    assert await llm_models.list_models("nope") == []


@pytest.mark.asyncio
async def test_openai_filter_excludes_non_chat_models(monkeypatch):
    class _R:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": [
                    {"id": "gpt-4o", "created": 3},
                    {"id": "text-embedding-3-small", "created": 9},
                    {"id": "whisper-1", "created": 9},
                    {"id": "gpt-4o-mini-tts", "created": 9},
                    {"id": "o3", "created": 5},
                    {"id": "dall-e-3", "created": 9},
                ]
            }

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **kw):
            return _R()

    monkeypatch.setattr(llm_models, "httpx", type("M", (), {"AsyncClient": _Client}))
    monkeypatch.setattr(llm_models.app_settings, "openai_api_key", "sk-test", raising=False)
    models = await llm_models._fetch_openai()
    assert models == ["o3", "gpt-4o"]  # created DESC, non-chat excluded
