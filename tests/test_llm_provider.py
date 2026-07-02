"""LLM provider abstraction tests — Wave 4 of plan 10 § B.4.

Coverage:
- `estimate_cost` per provider (Anthropic + OpenAI + Ollama=0).
- Factory routes correctly via `Settings.llm_provider`.
- Env-backed key resolution (plan 26 / 0.2.0.01: vault replaced by env).
- `tracked_call` wrapper logs to `ApiUsage` (with mock session).
- Retry policy: rate_limit → exponential backoff up to 3; timeout → retry
  once; schema_validation → re-prompt once; provider_error → fallback if set.

We don't hit live APIs in unit tests — providers are exercised against
mock async clients that mimic the SDK shape.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel

from llm.base import (
    CompletionResult,
    LLMProvider,
    LLMProviderError,
    StructuredResult,
)
from models import LLMProvider as LLMProviderEnum
from models import Settings

pytestmark = pytest.mark.uses_sample_data_shims


@pytest.fixture
def env_keys(monkeypatch):
    """Provide Anthropic + OpenAI env keys for factory tests."""
    from config import settings as app_settings

    monkeypatch.setattr(app_settings, "anthropic_api_key", "sk-ant-test-redacted")
    monkeypatch.setattr(app_settings, "openai_api_key", "sk-openai-test-redacted")
    return app_settings


# ── Cost estimation ────────────────────────────────────────────────────


def test_anthropic_estimate_cost() -> None:
    from llm.anthropic import AnthropicProvider

    p = AnthropicProvider(api_key="sk-test", model="claude-sonnet-4-6")
    cost = p.estimate_cost(input_tokens=1_000_000, output_tokens=1_000_000)
    # Sonnet: $3 input + $15 output per 1M tokens.
    assert abs(cost - 18.0) < 0.001


def test_openai_estimate_cost() -> None:
    from llm.openai import OpenAIProvider

    p = OpenAIProvider(api_key="sk-test", model="gpt-4o")
    cost = p.estimate_cost(input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(cost - 12.5) < 0.001


def test_ollama_cost_zero() -> None:
    from llm.ollama import OllamaProvider

    p = OllamaProvider(base_url="http://localhost:11434", model="llama3.1:70b")
    assert p.estimate_cost(input_tokens=1_000_000, output_tokens=1_000_000) == 0.0


def test_anthropic_unknown_model_falls_back() -> None:
    from llm.anthropic import AnthropicProvider

    p = AnthropicProvider(api_key="sk-test", model="claude-future-9999")
    cost = p.estimate_cost(input_tokens=1_000_000, output_tokens=1_000_000)
    assert cost > 0.0  # uses default rates


# ── Provider IDs / model names ─────────────────────────────────────────


def test_provider_ids() -> None:
    from llm.anthropic import AnthropicProvider
    from llm.ollama import OllamaProvider
    from llm.openai import OpenAIProvider

    assert AnthropicProvider(api_key="x").provider_id == "anthropic"
    assert OpenAIProvider(api_key="x").provider_id == "openai"
    assert OllamaProvider().provider_id == "ollama"


def test_provider_rejects_empty_api_key() -> None:
    from llm.anthropic import AnthropicProvider
    from llm.openai import OpenAIProvider

    with pytest.raises(LLMProviderError):
        AnthropicProvider(api_key="")
    with pytest.raises(LLMProviderError):
        OpenAIProvider(api_key="")


# ── Factory ────────────────────────────────────────────────────────────


def test_factory_anthropic(env_keys) -> None:
    from llm import get_provider

    settings = Settings(
        user_id=1, llm_provider=LLMProviderEnum.ANTHROPIC, llm_model="claude-sonnet-4-6"
    )

    provider = get_provider(settings)

    from llm.anthropic import AnthropicProvider

    assert isinstance(provider, AnthropicProvider)
    assert provider.model_name == "claude-sonnet-4-6"


def test_factory_openai(env_keys) -> None:
    from llm import get_provider

    settings = Settings(user_id=1, llm_provider=LLMProviderEnum.OPENAI, llm_model="gpt-4o")

    provider = get_provider(settings)

    from llm.openai import OpenAIProvider

    assert isinstance(provider, OpenAIProvider)


def test_factory_ollama_does_not_require_api_key() -> None:
    from llm import get_provider

    settings = Settings(user_id=1, llm_provider=LLMProviderEnum.OLLAMA, llm_model="llama3.1:70b")

    # Ollama doesn't need an api key (env-based now; OLLAMA_BASE_URL defaults
    # to http://localhost:11434).
    provider = get_provider(settings)

    from llm.ollama import OllamaProvider

    assert isinstance(provider, OllamaProvider)


def test_factory_fallback(env_keys) -> None:
    from llm import get_provider

    settings = Settings(
        user_id=1,
        llm_provider=LLMProviderEnum.ANTHROPIC,
        llm_fallback_provider=LLMProviderEnum.OLLAMA,
    )

    primary = get_provider(settings)
    fallback = get_provider(settings, fallback=True)

    assert primary.provider_id == "anthropic"
    assert fallback.provider_id == "ollama"


def test_factory_anthropic_missing_env_key_falls_back_to_env_resolved(monkeypatch) -> None:
    """0.7.0.48 fold-in: preferred provider lacks env key → factory falls back
    to env-resolved active provider (precedence ANTHROPIC > OPENAI > OLLAMA).
    Replaces the old "raise on empty env key" path that produced silent
    `auth_required` for fresh users whose `Settings.llm_provider` defaulted to
    ANTHROPIC but who'd only set `OPENAI_API_KEY` in `.env`.
    """
    from config import settings as app_settings
    from llm import get_provider
    from llm.openai import OpenAIProvider

    monkeypatch.setattr(app_settings, "anthropic_api_key", None)
    monkeypatch.setattr(app_settings, "openai_api_key", "sk-openai-fallback")
    settings = Settings(user_id=1, llm_provider=LLMProviderEnum.ANTHROPIC, llm_model="gpt-4o")
    provider = get_provider(settings)
    assert isinstance(provider, OpenAIProvider)


def test_factory_raises_when_nothing_configured(monkeypatch) -> None:
    """0.7.0.48 fold-in: when NO provider has env keys, factory raises
    `auth_required` with operator-actionable guidance. Ollama is normally
    always env-configured (default `OLLAMA_BASE_URL`), so this test must
    explicitly None it out alongside the cloud keys.
    """
    from config import settings as app_settings
    from llm import get_provider

    monkeypatch.setattr(app_settings, "anthropic_api_key", None)
    monkeypatch.setattr(app_settings, "openai_api_key", None)
    monkeypatch.setattr(app_settings, "ollama_base_url", None)
    settings = Settings(
        user_id=1, llm_provider=LLMProviderEnum.ANTHROPIC, llm_model="claude-sonnet-4-6"
    )
    with pytest.raises(LLMProviderError) as exc_info:
        get_provider(settings)
    assert exc_info.value.kind == "auth_required"
    assert ".env" in str(exc_info.value)


# ── tracked_call ───────────────────────────────────────────────────────


class _Schema(BaseModel):
    foo: str
    bar: int = 0


class _StubProvider(LLMProvider):
    def __init__(self) -> None:
        self.calls = 0
        self.fail_for: list[Exception] = []

    @property
    def model_name(self) -> str:
        return "stub-model"

    @property
    def provider_id(self) -> str:
        return "anthropic"

    async def complete(self, prompt: str, *, max_tokens: int = 1024):
        self.calls += 1
        if self.fail_for:
            raise self.fail_for.pop(0)
        return CompletionResult(text="ok", input_tokens=10, output_tokens=20, model=self.model_name)

    async def structured(self, prompt: str, schema, *, max_tokens: int = 1024):
        self.calls += 1
        if self.fail_for:
            raise self.fail_for.pop(0)
        return StructuredResult(
            text='{"foo":"x","bar":1}',
            value={"foo": "x", "bar": 1},
            input_tokens=8,
            output_tokens=12,
            model=self.model_name,
        )

    async def stream(self, prompt: str, *, max_tokens: int = 1024):
        self.calls += 1

        async def gen():
            yield "chunk1"
            yield "chunk2"

        return gen()

    def estimate_cost(self, *, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens + output_tokens) * 0.0001


async def test_tracked_call_logs_success(capsys) -> None:
    from services.llm_tracker import tracked_call

    p = _StubProvider()
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    result = await tracked_call(
        session=session,
        user_id=1,
        provider=p,
        method="complete",
        prompt="hi",
    )
    assert isinstance(result, CompletionResult)
    assert session.add.call_count == 1
    row = session.add.call_args.args[0]
    assert row.succeeded is True
    assert row.input_tokens == 10
    assert row.output_tokens == 20
    assert row.cost_usd > 0


async def test_tracked_call_retries_on_rate_limit() -> None:
    from services.llm_tracker import tracked_call

    p = _StubProvider()
    p.fail_for = [
        LLMProviderError("rate limited", kind="rate_limit"),
        LLMProviderError("rate limited", kind="rate_limit"),
    ]
    # No session — log misses are tolerated.
    result = await tracked_call(
        session=None,
        user_id=1,
        provider=p,
        method="complete",
        prompt="hi",
    )
    assert isinstance(result, CompletionResult)
    assert p.calls == 3  # 2 fails + 1 success


async def test_tracked_call_falls_back_on_500() -> None:
    from services.llm_tracker import tracked_call

    primary = _StubProvider()
    primary.fail_for = [LLMProviderError("upstream 500", kind="provider_error")]
    fallback = _StubProvider()

    result = await tracked_call(
        session=None,
        user_id=1,
        provider=primary,
        fallback_provider=fallback,
        method="complete",
        prompt="hi",
    )
    assert isinstance(result, CompletionResult)
    assert primary.calls == 1
    assert fallback.calls == 1


async def test_tracked_call_raises_after_retries_exhausted() -> None:
    from services.llm_tracker import tracked_call

    p = _StubProvider()
    p.fail_for = [
        LLMProviderError("rate limited", kind="rate_limit"),
        LLMProviderError("rate limited", kind="rate_limit"),
        LLMProviderError("rate limited", kind="rate_limit"),
        LLMProviderError("rate limited", kind="rate_limit"),
    ]
    with pytest.raises(LLMProviderError):
        await tracked_call(
            session=None,
            user_id=1,
            provider=p,
            method="complete",
            prompt="hi",
        )
    # 1 initial + 3 retries = 4 calls total.
    assert p.calls == 4


async def test_tracked_call_persists_failure_row() -> None:
    from services.llm_tracker import tracked_call

    p = _StubProvider()
    p.fail_for = [LLMProviderError("provider fail", kind="provider_error")]

    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    with pytest.raises(LLMProviderError):
        await tracked_call(
            session=session,
            user_id=1,
            provider=p,
            method="complete",
            prompt="hi",
        )

    # One failure row persisted.
    assert session.add.call_count == 1
    row = session.add.call_args.args[0]
    assert row.succeeded is False
    assert row.error_kind == "provider_error"
