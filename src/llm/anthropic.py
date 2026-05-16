"""Anthropic Claude provider — tool-use for structured output.

Per BACKEND.md § M.2. Pricing as of Phase 1: Claude 3.5 Sonnet at
$3/M input + $15/M output tokens (2026-04 rate sheet).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import TypeVar

from anthropic import AsyncAnthropic
from pydantic import BaseModel

from .base import (
    CompletionResult,
    LLMProvider,
    LLMProviderError,
    StructuredResult,
)

T = TypeVar("T", bound=BaseModel)

# USD per million tokens; updated when Anthropic's pricing changes.
_PRICING = {
    "claude-3.5-sonnet-20250219": {"input": 3.0, "output": 15.0},
    "claude-3.5-haiku-20250219": {"input": 0.80, "output": 4.0},
    # Default fallback if a future model isn't on this sheet.
    "_default": {"input": 3.0, "output": 15.0},
}


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "claude-3.5-sonnet-20250219") -> None:
        if not api_key:
            raise LLMProviderError("anthropic api_key is empty", kind="auth_required")
        self._model = model
        self._client = AsyncAnthropic(api_key=api_key)

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider_id(self) -> str:
        return "anthropic"

    async def complete(self, prompt: str, *, max_tokens: int = 1024) -> CompletionResult:
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:  # noqa: BLE001 — narrow at retry layer
            raise LLMProviderError(f"anthropic complete failed: {exc}") from exc

        text = "".join(block.text for block in response.content if hasattr(block, "text"))
        return CompletionResult(
            text=text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=self._model,
        )

    async def structured(
        self,
        prompt: str,
        schema: type[T],
        *,
        max_tokens: int = 1024,
    ) -> StructuredResult:
        """Tool-use structured output: define a single tool whose input_schema
        matches the Pydantic schema; force the model to call it."""
        tool_name = schema.__name__.lower()
        tool_def = {
            "name": tool_name,
            "description": (schema.__doc__ or "Structured output").strip(),
            "input_schema": schema.model_json_schema(),
        }
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                tools=[tool_def],
                tool_choice={"type": "tool", "name": tool_name},
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:  # noqa: BLE001
            raise LLMProviderError(f"anthropic structured failed: {exc}") from exc

        tool_input: dict = {}
        text_chunks: list[str] = []
        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
                tool_input = block.input
            elif hasattr(block, "text"):
                text_chunks.append(block.text)

        return StructuredResult(
            text=json.dumps(tool_input),
            value=tool_input,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=self._model,
        )

    async def stream(
        self,
        prompt: str,
        *,
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        try:
            async with self._client.messages.stream(
                model=self._model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                async for chunk in stream.text_stream:
                    yield chunk
        except Exception as exc:  # noqa: BLE001
            raise LLMProviderError(f"anthropic stream failed: {exc}") from exc

    def estimate_cost(self, *, input_tokens: int, output_tokens: int) -> float:
        rates = _PRICING.get(self._model, _PRICING["_default"])
        return (input_tokens / 1_000_000) * rates["input"] + (output_tokens / 1_000_000) * rates[
            "output"
        ]
