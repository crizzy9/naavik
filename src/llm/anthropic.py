"""Anthropic Claude provider — tool-use for structured output.

Per BACKEND.md § M.2. Pricing as of Phase 1: Claude 3.5 Sonnet at
$3/M input + $15/M output tokens (2026-04 rate sheet).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
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


@dataclass(slots=True)
class BatchRequest:
    """One request inside an Anthropic batch submit.

    `custom_id` lets the caller match results back to inputs even when
    the batch API reorders responses.
    """

    custom_id: str
    prompt: str
    schema: type[BaseModel]
    max_tokens: int = 1024
    system: str | None = None
    cache_system: bool = False


@dataclass(slots=True)
class BatchResponse:
    """One result row from `AnthropicProvider.batch`."""

    custom_id: str
    value: dict = field(default_factory=dict)
    text: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    succeeded: bool = True
    error: str | None = None


# USD per million tokens; updated when Anthropic's pricing changes.
_PRICING = {
    "claude-opus-4-8": {"input": 5.0, "output": 25.0},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0},
    # Default fallback if a future model isn't on this sheet.
    "_default": {"input": 5.0, "output": 25.0},
}


class AnthropicProvider(LLMProvider):
    DEFAULT_MODEL = "claude-opus-4-8"

    def __init__(self, api_key: str, model: str | None = DEFAULT_MODEL) -> None:
        if not api_key:
            raise LLMProviderError("anthropic api_key is empty", kind="auth_required")
        # `model=None` means "use the provider default" — the cross-provider
        # fallback in `llm.get_provider` passes None when the stored model
        # belongs to a different provider.
        self._model = model or self.DEFAULT_MODEL
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
        system: str | None = None,
        cache_system: bool = False,
    ) -> StructuredResult:
        """Tool-use structured output: define a single tool whose input_schema
        matches the Pydantic schema; force the model to call it.

        Plan 66 (0.3.1) — `system` carries the cacheable constitution + voice
        corpus prefix; `cache_system=True` attaches `cache_control` so the
        prefix reuses a 5-minute ephemeral cache across the bundle's stages.
        OpenAI + Ollama providers ignore `cache_system` (no caching).
        """
        tool_name = schema.__name__.lower()
        tool_def = {
            "name": tool_name,
            "description": (schema.__doc__ or "Structured output").strip(),
            "input_schema": schema.model_json_schema(),
        }
        create_kwargs: dict = {
            "model": self._model,
            "max_tokens": max_tokens,
            "tools": [tool_def],
            "tool_choice": {"type": "tool", "name": tool_name},
            "messages": [{"role": "user", "content": prompt}],
        }
        if system is not None:
            if cache_system:
                create_kwargs["system"] = [
                    {
                        "type": "text",
                        "text": system,
                        "cache_control": {"type": "ephemeral"},
                    }
                ]
            else:
                create_kwargs["system"] = system
        try:
            response = await self._client.messages.create(**create_kwargs)
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

    def estimate_cost(
        self, *, input_tokens: int, output_tokens: int, model: str | None = None
    ) -> float:
        rates = _PRICING.get(self._model, _PRICING["_default"])
        return (input_tokens / 1_000_000) * rates["input"] + (output_tokens / 1_000_000) * rates[
            "output"
        ]

    async def tool_use(self, **create_kwargs):
        """Raw tool-use `messages.create` passthrough (plan 91 6.4).

        The tool-loop orchestrator needs the unabridged Anthropic response
        (tool_use blocks + text blocks), which doesn't fit the
        `complete()`/`structured()` result shapes — but reaching into
        `provider._client` from services bypassed the provider surface
        entirely. Raises `LLMProviderError` on failure like every other
        method so callers get uniform error handling.
        """
        try:
            return await self._client.messages.create(**create_kwargs)
        except Exception as exc:  # noqa: BLE001
            raise LLMProviderError(f"anthropic tool_use failed: {exc}") from exc

    async def batch(
        self,
        requests: list[BatchRequest],
        *,
        poll_interval_seconds: float = 5.0,
        timeout_seconds: float = 300.0,
    ) -> list[BatchResponse]:
        """Submit `requests` via Anthropic's Message Batches API + poll.

        Plan 67 (0.3.4) § C.2 / T3 / E.2. 50% cost discount vs synchronous
        per-request calls. Polls every `poll_interval_seconds` until the
        batch reaches a terminal state (`ended`) or `timeout_seconds` passes.

        Returns BatchResponse rows in the same order as the input requests
        (matched via `custom_id`). On polling timeout / batch failure,
        raises `LLMProviderError` so the council code can fall back to
        synchronous `asyncio.gather`.
        """
        if not requests:
            return []

        batch_requests = []
        for req in requests:
            tool_name = req.schema.__name__.lower()
            params: dict = {
                "model": self._model,
                "max_tokens": req.max_tokens,
                "tools": [
                    {
                        "name": tool_name,
                        "description": (req.schema.__doc__ or "Structured output").strip(),
                        "input_schema": req.schema.model_json_schema(),
                    }
                ],
                "tool_choice": {"type": "tool", "name": tool_name},
                "messages": [{"role": "user", "content": req.prompt}],
            }
            if req.system is not None:
                if req.cache_system:
                    params["system"] = [
                        {
                            "type": "text",
                            "text": req.system,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ]
                else:
                    params["system"] = req.system
            batch_requests.append({"custom_id": req.custom_id, "params": params})

        try:
            created = await self._client.messages.batches.create(requests=batch_requests)
        except Exception as exc:  # noqa: BLE001
            raise LLMProviderError(f"anthropic batch submit failed: {exc}") from exc

        batch_id = getattr(created, "id", None)
        if batch_id is None:
            raise LLMProviderError("anthropic batch submit returned no id")

        elapsed = 0.0
        while elapsed < timeout_seconds:
            try:
                status = await self._client.messages.batches.retrieve(batch_id)
            except Exception as exc:  # noqa: BLE001
                raise LLMProviderError(f"anthropic batch poll failed: {exc}") from exc
            processing = getattr(status, "processing_status", None)
            if processing == "ended":
                break
            await asyncio.sleep(poll_interval_seconds)
            elapsed += poll_interval_seconds
        else:
            raise LLMProviderError(
                f"anthropic batch {batch_id} did not converge within {timeout_seconds}s"
            )

        # Pull results
        try:
            stream = await self._client.messages.batches.results(batch_id)
        except Exception as exc:  # noqa: BLE001
            raise LLMProviderError(f"anthropic batch results fetch failed: {exc}") from exc

        results_by_id: dict[str, BatchResponse] = {}
        async for row in stream:
            cid = getattr(row, "custom_id", "") or ""
            result = getattr(row, "result", None)
            result_type = getattr(result, "type", "")
            if result_type != "succeeded" or result is None:
                results_by_id[cid] = BatchResponse(
                    custom_id=cid,
                    succeeded=False,
                    error=str(getattr(result, "error", None) or "batch_request_failed"),
                )
                continue
            message = getattr(result, "message", None)
            content = getattr(message, "content", []) or []
            tool_input: dict = {}
            text_chunks: list[str] = []
            for block in content:
                if getattr(block, "type", None) == "tool_use":
                    tool_input = getattr(block, "input", {}) or {}
                elif hasattr(block, "text"):
                    text_chunks.append(block.text)
            usage = getattr(message, "usage", None)
            input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
            output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
            results_by_id[cid] = BatchResponse(
                custom_id=cid,
                value=tool_input,
                text=json.dumps(tool_input) if tool_input else "".join(text_chunks),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                succeeded=True,
            )

        return [
            results_by_id.get(
                req.custom_id, BatchResponse(custom_id=req.custom_id, succeeded=False)
            )
            for req in requests
        ]
