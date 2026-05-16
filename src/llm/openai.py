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


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gpt-4o") -> None:
        if not api_key:
            raise LLMProviderError("openai api_key is empty", kind="auth_required")
        self._model = model
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

    async def structured(
        self,
        prompt: str,
        schema: type[T],
        *,
        max_tokens: int = 1024,
    ) -> StructuredResult:
        json_schema = {
            "name": schema.__name__,
            "schema": schema.model_json_schema(),
            "strict": True,
        }
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                max_tokens=max_tokens,
                response_format={"type": "json_schema", "json_schema": json_schema},
                messages=[{"role": "user", "content": prompt}],
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

    def estimate_cost(self, *, input_tokens: int, output_tokens: int) -> float:
        rates = _PRICING.get(self._model, _PRICING["_default"])
        return (input_tokens / 1_000_000) * rates["input"] + (output_tokens / 1_000_000) * rates[
            "output"
        ]
