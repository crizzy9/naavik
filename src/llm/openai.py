"""OpenAI provider — `response_format=json_schema` for structured output.

Per BACKEND.md § M.2. Pricing as of Phase 1: gpt-4o at
$2.50/M input + $10/M output (2026-04 rate sheet).
"""

from __future__ import annotations

import copy
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
    # Embedding models (plan 91 6.5) — priced per input token only.
    "text-embedding-3-small": {"input": 0.02, "output": 0.0},
    "text-embedding-3-large": {"input": 0.13, "output": 0.0},
}

# Plan 61 / 0.2.7.16 — Matryoshka-truncated to 768d via `dimensions` SDK kwarg.
# Same `text-embedding-3-small` model used for the per-job + per-question
# embedding pipeline.
_EMBEDDING_MODEL = "text-embedding-3-small"
_EMBEDDING_DIM = 768


class OpenAIProvider(LLMProvider):
    """All chat calls send `max_completion_tokens` — post-gpt-4o model
    families (gpt-5.x, o-series) reject the legacy `max_tokens` param with a
    400, and the older models accept the new name. This surfaced the moment
    item 10 made the SELECTED model actually reach the wire."""

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
                max_completion_tokens=max_tokens,
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
    def _to_strict_schema(root: dict) -> bool:
        """Make a Pydantic JSON schema OpenAI-strict, in place.

        `strict: true` json_schema mode requires every object to carry
        `additionalProperties: false` and to list ALL properties in
        `required` (optional fields express optionality via a null-union
        type, which Pydantic already emits for `X | None`). Without this
        the API rejects the request with `'additionalProperties' is
        required to be supplied and to be false`.

        Strict mode also forbids `default` (anywhere) and `$ref` with
        sibling keywords. Pydantic emits both for enum fields with
        defaults — e.g. `remote_policy: RemotePolicy = RemotePolicy.UNKNOWN`
        becomes `{"$ref": "#/$defs/RemotePolicy", "default": "unknown"}` —
        which the API rejects with `$ref cannot have keywords {'default'}`.
        We strip every `default` and inline any `$ref` that still carries
        siblings (siblings win over the resolved target on key conflicts).

        Returns True when the transformed schema is strict-compatible.
        Map-style objects (`dict[str, X]` → schema-valued
        `additionalProperties`, no fixed `properties` — e.g.
        `JobScore.per_dimension`) are fundamentally inexpressible in strict
        mode; those nodes are left intact and the caller must send
        `strict: false` (best-effort JSON schema; Pydantic re-validates
        downstream).
        """
        defs = root.get("$defs", {})
        strict_ok = True

        def _resolve(ref: str) -> dict | None:
            name = ref.removeprefix("#/$defs/")
            target = defs.get(name) if name != ref else None
            return target if isinstance(target, dict) else None

        def _walk(node: object) -> None:
            nonlocal strict_ok
            if isinstance(node, dict):
                node.pop("default", None)
                ref = node.get("$ref")
                if isinstance(ref, str) and len(node) > 1:
                    target = _resolve(ref)
                    siblings = {k: v for k, v in node.items() if k != "$ref"}
                    node.clear()
                    if target is not None:
                        node.update(copy.deepcopy(target))
                        node.update(siblings)
                    else:
                        # Unresolvable ref (non-$defs pointer): a bare $ref is
                        # the only strict-legal form, so drop the siblings.
                        node["$ref"] = ref
                if isinstance(node.get("additionalProperties"), dict):
                    # dict[str, X] map — keep the map schema, drop strict.
                    strict_ok = False
                elif node.get("type") == "object" or "properties" in node:
                    props = node.get("properties", {})
                    node["additionalProperties"] = False
                    node["required"] = list(props.keys())
                for value in node.values():
                    _walk(value)
            elif isinstance(node, list):
                for value in node:
                    _walk(value)

        _walk(root)
        return strict_ok

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
        strict_ok = self._to_strict_schema(strict_schema)
        json_schema = {
            "name": schema.__name__,
            "schema": strict_schema,
            "strict": strict_ok,
        }
        messages: list[dict] = []
        if system is not None:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                max_completion_tokens=max_tokens,
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
                max_completion_tokens=max_tokens,
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

    def estimate_cost(
        self, *, input_tokens: int, output_tokens: int, model: str | None = None
    ) -> float:
        target = model or self._model
        # Embedding results report "<model>@<dim>" — strip the dim suffix.
        rates = (
            _PRICING.get(target) or _PRICING.get(target.split("@", 1)[0]) or (_PRICING["_default"])
        )
        return (input_tokens / 1_000_000) * rates["input"] + (output_tokens / 1_000_000) * rates[
            "output"
        ]
