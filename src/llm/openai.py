"""OpenAI provider — `response_format=json_schema` for structured output.

Per BACKEND.md § M.2. Pricing as of Phase 1: gpt-4o at
$2.50/M input + $10/M output (2026-04 rate sheet).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel

from .base import (
    CompletionResult,
    EmbeddingResult,
    LLMProvider,
    LLMProviderError,
    StructuredResult,
)

T = TypeVar("T", bound=BaseModel)

_PRICING = {
    "gpt-4o": {"input": 2.50, "output": 10.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "_default": {"input": 2.50, "output": 10.0},
}

# Plan 61 / 0.2.7.16 — Matryoshka-truncated to 768d via `dimensions` SDK kwarg.
# Same `text-embedding-3-small` model used for the per-job + per-question
# embedding pipeline.
_EMBEDDING_MODEL = "text-embedding-3-small"
_EMBEDDING_DIM = 768


class OpenAIProvider(LLMProvider):
    DEFAULT_MODEL = "gpt-4o"

    def __init__(self, api_key: str, model: str | None = DEFAULT_MODEL) -> None:
        if not api_key:
            raise LLMProviderError("openai api_key is empty", kind="auth_required")
        # None → provider default (cross-provider fallback in llm.get_provider).
        self._model = model or self.DEFAULT_MODEL
        self._client = AsyncOpenAI(api_key=api_key)

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider_id(self) -> str:
        return "openai"

    async def complete(self, prompt: str, *, max_tokens: int = 1024) -> CompletionResult:
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:  # noqa: BLE001
            raise LLMProviderError(f"openai complete failed: {exc}") from exc

        choice = response.choices[0]
        usage = response.usage
        return CompletionResult(
            text=choice.message.content or "",
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            model=self._model,
        )

    @staticmethod
    def _to_strict_schema(node: object) -> None:
        """Make a Pydantic JSON schema OpenAI-strict, in place.

        `strict: true` json_schema mode requires every object to carry
        `additionalProperties: false` and to list ALL properties in
        `required` (optional fields express optionality via a null-union
        type, which Pydantic already emits for `X | None`). Without this
        the API rejects the request with `'additionalProperties' is
        required to be supplied and to be false`.
        """
        if isinstance(node, dict):
            if node.get("type") == "object" or "properties" in node:
                props = node.get("properties", {})
                node["additionalProperties"] = False
                node["required"] = list(props.keys())
            for value in node.values():
                OpenAIProvider._to_strict_schema(value)
        elif isinstance(node, list):
            for value in node:
                OpenAIProvider._to_strict_schema(value)

    async def structured(
        self,
        prompt: str,
        schema: type[T],
        *,
        max_tokens: int = 1024,
        system: str | None = None,
        cache_system: bool = False,  # noqa: ARG002 — accepted for interface parity; OpenAI doesn't cache
    ) -> StructuredResult:
        strict_schema = schema.model_json_schema()
        self._to_strict_schema(strict_schema)
        json_schema = {
            "name": schema.__name__,
            "schema": strict_schema,
            "strict": True,
        }
        messages: list[dict] = []
        if system is not None:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                max_tokens=max_tokens,
                response_format={"type": "json_schema", "json_schema": json_schema},
                messages=messages,
            )
        except Exception as exc:  # noqa: BLE001
            raise LLMProviderError(f"openai structured failed: {exc}") from exc

        choice = response.choices[0]
        raw_text = choice.message.content or "{}"
        try:
            value = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise LLMProviderError(
                f"openai structured response not valid JSON: {raw_text!r}",
                kind="schema_validation",
            ) from exc

        usage = response.usage
        return StructuredResult(
            text=raw_text,
            value=value,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            model=self._model,
        )

    async def stream(
        self,
        prompt: str,
        *,
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        try:
            stream = await self._client.chat.completions.create(
                model=self._model,
                max_tokens=max_tokens,
                stream=True,
                messages=[{"role": "user", "content": prompt}],
            )
            async for event in stream:
                choice = event.choices[0] if event.choices else None
                delta = choice.delta if choice else None
                if delta and delta.content:
                    yield delta.content
        except Exception as exc:  # noqa: BLE001
            raise LLMProviderError(f"openai stream failed: {exc}") from exc

    async def embed(self, text: str) -> EmbeddingResult:
        try:
            response = await self._client.embeddings.create(
                model=_EMBEDDING_MODEL,
                input=text,
                dimensions=_EMBEDDING_DIM,
            )
        except Exception as exc:  # noqa: BLE001
            raise LLMProviderError(f"openai embed failed: {exc}") from exc

        vector = list(response.data[0].embedding)
        usage = getattr(response, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", 0) if usage is not None else 0
        return EmbeddingResult(
            vector=vector,
            input_tokens=int(prompt_tokens),
            output_tokens=0,
            model=f"{_EMBEDDING_MODEL}@{_EMBEDDING_DIM}",
        )

    def estimate_cost(self, *, input_tokens: int, output_tokens: int) -> float:
        rates = _PRICING.get(self._model, _PRICING["_default"])
        return (input_tokens / 1_000_000) * rates["input"] + (output_tokens / 1_000_000) * rates[
            "output"
        ]
