"""Provider-agnostic LLM interface.

Per BACKEND.md § M.1. Three concrete implementations: Anthropic Claude
(tool-use structured output), OpenAI (`response_format=json_schema`), and
Ollama (JSON mode, local).

Service layer always goes through `LLMProvider`; never imports the SDK
clients directly. `services/llm_tracker.tracked_call` wraps every call so
cost + tokens log to `ApiUsage` automatically.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMProviderError(Exception):
    """Raised when a provider call fails irrecoverably (after retries)."""

    def __init__(self, message: str, *, kind: str = "provider_error") -> None:
        super().__init__(message)
        self.kind = kind


class LLMProvider(ABC):
    """Abstract LLM provider. Every concrete impl exposes the same surface."""

    @abstractmethod
    async def complete(self, prompt: str, *, max_tokens: int = 1024) -> CompletionResult:
        """Plain text completion. Returns text + token counts."""

    @abstractmethod
    async def structured(
        self,
        prompt: str,
        schema: type[T],
        *,
        max_tokens: int = 1024,
        system: str | None = None,
        cache_system: bool = False,
    ) -> StructuredResult[T]:
        """Structured output validated against the Pydantic `schema`.

        `system` carries the (optional) system-message prefix. When
        `cache_system=True`, providers that support prompt caching
        (Anthropic) attach the appropriate `cache_control` marker so the
        prefix reuses an ephemeral cache across calls. Other providers
        accept the kwarg silently — caching is a no-op there.
        """

    @abstractmethod
    async def stream(
        self,
        prompt: str,
        *,
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        """Stream completion as text chunks."""

    @abstractmethod
    def estimate_cost(self, *, input_tokens: int, output_tokens: int) -> float:
        """USD cost estimate per provider's pricing sheet."""

    async def embed(self, text: str) -> EmbeddingResult:
        """Dense vector embedding (plan 61 / 0.2.7.16).

        Anthropic doesn't offer embeddings — subclasses that route to a
        completion-only API raise here. OpenAI + Ollama override.
        """
        raise LLMProviderError(
            f"{self.provider_id} does not offer embeddings. Configure "
            "Settings.embedding_provider = 'openai' or 'ollama' for "
            "semantic match.",
            kind="embed_unsupported",
        )

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Concrete model id (e.g. `claude-sonnet-4-6`)."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Stable provider identifier — `anthropic` | `openai` | `ollama`."""


class CompletionResult(BaseModel):
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str


class EmbeddingResult(BaseModel):
    """Return shape for `LLMProvider.embed` (plan 61 / 0.2.7.16)."""

    vector: list[float]
    input_tokens: int = 0
    output_tokens: int = 0
    model: str


class StructuredResult(BaseModel):
    """Generic-ish wrapper. Subclasses bind `value` to a concrete `T`."""

    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str
    # `value` carries the parsed Pydantic object; we store as `dict` here for
    # easy validation upstream (Pydantic generic model would force runtime
    # `model_rebuild` gymnastics on every callsite).
    value: dict
