"""Embedding-provider dispatch + Anthropic rejection — plan 61 (0.2.7.16).

Covers `LLMProvider.embed` default + OpenAI/Ollama overrides + the
`get_embedding_provider` resolver against env-presence.
"""

from __future__ import annotations

import os

os.environ.setdefault("NAAVIK_DEBUG", "1")

import pytest  # noqa: E402

from llm import get_embedding_provider  # noqa: E402
from llm.base import EmbeddingResult, LLMProviderError  # noqa: E402
from llm.ollama import OllamaProvider  # noqa: E402
from llm.openai import OpenAIProvider  # noqa: E402

pytestmark = pytest.mark.uses_sample_data_shims

# ── ABC default ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_anthropic_embed_raises():
    """Anthropic doesn't offer embeddings; calling embed must raise."""
    from llm.anthropic import AnthropicProvider

    provider = AnthropicProvider(api_key="sk-test", model="claude-3.5-sonnet-20250219")
    with pytest.raises(LLMProviderError) as exc:
        await provider.embed("text")
    assert exc.value.kind == "embed_unsupported"
    # Hint must mention the migration path
    assert "embedding" in str(exc.value).lower()


# ── OpenAI ──────────────────────────────────────────────────────────────


class _FakeOpenAIResponse:
    def __init__(self, vector: list[float], prompt_tokens: int = 5):
        self.data = [type("D", (), {"embedding": vector})()]
        self.usage = type("U", (), {"prompt_tokens": prompt_tokens})()


class _FakeOpenAIEmbeddings:
    def __init__(self, response: _FakeOpenAIResponse):
        self._response = response
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


class _FakeOpenAIClient:
    def __init__(self, response: _FakeOpenAIResponse):
        self.embeddings = _FakeOpenAIEmbeddings(response)


@pytest.mark.asyncio
async def test_openai_embed_round_trip_768d():
    provider = OpenAIProvider(api_key="sk-test", model="gpt-4o")
    fake_vector = [float(i) / 1000.0 for i in range(768)]
    provider._client = _FakeOpenAIClient(_FakeOpenAIResponse(fake_vector, prompt_tokens=42))

    result = await provider.embed("some text")
    assert isinstance(result, EmbeddingResult)
    assert len(result.vector) == 768
    assert result.input_tokens == 42
    assert result.output_tokens == 0
    # Model identifier includes the Matryoshka-truncated dim suffix.
    assert result.model == "text-embedding-3-small@768"
    # SDK call requested dimensions=768
    call = provider._client.embeddings.calls[0]
    assert call["dimensions"] == 768
    assert call["model"] == "text-embedding-3-small"


@pytest.mark.asyncio
async def test_openai_embed_wraps_sdk_error():
    provider = OpenAIProvider(api_key="sk-test", model="gpt-4o")

    class _BoomEmbeddings:
        async def create(self, **kwargs):
            raise RuntimeError("network down")

    provider._client = type("C", (), {"embeddings": _BoomEmbeddings()})()

    with pytest.raises(LLMProviderError) as exc:
        await provider.embed("text")
    assert "openai embed failed" in str(exc.value)


# ── Ollama ──────────────────────────────────────────────────────────────


class _FakeHttpResponse:
    def __init__(self, json_payload: dict):
        self._json = json_payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._json


class _FakeHttpClient:
    def __init__(self, response: _FakeHttpResponse):
        self._response = response
        self.calls: list[dict] = []

    async def post(self, url: str, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return self._response


@pytest.mark.asyncio
async def test_ollama_embed_round_trip_native_dim():
    provider = OllamaProvider(base_url="http://localhost:11434", model="llama3.1:70b")
    fake_vector = [0.0] * 768
    fake_resp = _FakeHttpResponse({"embedding": fake_vector, "prompt_eval_count": 8})
    provider._client = _FakeHttpClient(fake_resp)

    result = await provider.embed("some text")
    assert isinstance(result, EmbeddingResult)
    assert len(result.vector) == 768
    assert result.input_tokens == 8
    assert result.model == "nomic-embed-text"
    # SDK call targets the embeddings endpoint with the right model.
    call = provider._client.calls[0]
    assert call["url"].endswith("/api/embeddings")
    assert call["json"]["model"] == "nomic-embed-text"


@pytest.mark.asyncio
async def test_ollama_embed_rejects_missing_vector():
    provider = OllamaProvider(base_url="http://localhost:11434", model="llama3.1:70b")
    fake_resp = _FakeHttpResponse({"prompt_eval_count": 0})  # no embedding key
    provider._client = _FakeHttpClient(fake_resp)

    with pytest.raises(LLMProviderError) as exc:
        await provider.embed("text")
    assert exc.value.kind == "schema_validation"


# ── Resolver ────────────────────────────────────────────────────────────


def _settings_stub(
    *,
    enabled: bool = True,
    provider: str | None = None,
    user_id: int = 1,
    llm_model: str = "gpt-4o",
):
    """Lightweight Settings-shape stub for resolver tests."""
    from models import Settings

    return Settings(
        user_id=user_id,
        semantic_match_enabled=enabled,
        embedding_provider=provider,
        llm_model=llm_model,
    )


def test_resolver_returns_none_when_disabled():
    s = _settings_stub(enabled=False)
    assert get_embedding_provider(s) is None


def test_resolver_returns_none_when_anthropic():
    s = _settings_stub(provider="anthropic")
    assert get_embedding_provider(s) is None


def test_resolver_picks_openai_when_selected_and_key_present(monkeypatch):
    monkeypatch.setattr("config.settings.openai_api_key", "sk-test")
    monkeypatch.setattr("config.settings.ollama_base_url", "")
    s = _settings_stub(provider="openai")
    p = get_embedding_provider(s)
    assert p is not None
    assert p.provider_id == "openai"


def test_resolver_returns_none_for_openai_without_key(monkeypatch):
    monkeypatch.setattr("config.settings.openai_api_key", None)
    s = _settings_stub(provider="openai")
    assert get_embedding_provider(s) is None


def test_resolver_picks_ollama_when_selected(monkeypatch):
    monkeypatch.setattr("config.settings.ollama_base_url", "http://localhost:11434")
    s = _settings_stub(provider="ollama")
    p = get_embedding_provider(s)
    assert p is not None
    assert p.provider_id == "ollama"


def test_resolver_fallback_prefers_ollama_when_both_set(monkeypatch):
    monkeypatch.setattr("config.settings.openai_api_key", "sk-test")
    monkeypatch.setattr("config.settings.ollama_base_url", "http://localhost:11434")
    s = _settings_stub(provider=None)
    p = get_embedding_provider(s)
    assert p is not None
    assert p.provider_id == "ollama"


def test_resolver_fallback_returns_none_when_no_env(monkeypatch):
    monkeypatch.setattr("config.settings.openai_api_key", None)
    monkeypatch.setattr("config.settings.ollama_base_url", "")
    s = _settings_stub(provider=None)
    assert get_embedding_provider(s) is None
