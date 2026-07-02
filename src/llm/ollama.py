"""Ollama provider — local model via Ollama HTTP API.

Per BACKEND.md § M.2. Cost = $0 (local). Structured output via JSON mode
(`format: "json"`).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import TypeVar

import httpx
from pydantic import BaseModel

from .base import (
    CompletionResult,
    EmbeddingResult,
    LLMProvider,
    LLMProviderError,
    StructuredResult,
)

T = TypeVar("T", bound=BaseModel)

# Plan 61 / 0.2.7.16 — nomic-embed-text returns 768d native; no truncation.
_EMBEDDING_MODEL = "nomic-embed-text"


class OllamaProvider(LLMProvider):
    DEFAULT_MODEL = "llama3.1:70b"

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str | None = DEFAULT_MODEL,
    ) -> None:
        # None → provider default (cross-provider fallback in llm.get_provider).
        self._model = model or self.DEFAULT_MODEL
        self._base = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(120.0))

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider_id(self) -> str:
        return "ollama"

    async def complete(self, prompt: str, *, max_tokens: int = 1024) -> CompletionResult:
        try:
            r = await self._client.post(
                f"{self._base}/api/generate",
                json={
                    "model": self._model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": max_tokens},
                },
            )
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"ollama complete failed: {exc}") from exc

        data = r.json()
        return CompletionResult(
            text=data.get("response", ""),
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
            model=self._model,
        )

    async def structured(
        self,
        prompt: str,
        schema: type[T],
        *,
        max_tokens: int = 1024,
        system: str | None = None,
        cache_system: bool = False,  # noqa: ARG002 — Ollama doesn't cache
    ) -> StructuredResult:
        # Ollama "format: json" forces JSON output. We rely on the prompt to
        # describe the schema since Ollama doesn't natively bind to a JSON
        # schema. We append the schema to the prompt to bias the model.
        # `system` is prepended verbatim (no cache support).
        body = prompt if system is None else f"{system}\n\n---\n\n{prompt}"
        full_prompt = (
            f"{body}\n\n"
            f"Respond with a JSON object matching this schema exactly:\n"
            f"{json.dumps(schema.model_json_schema(), indent=2)}\n"
            f"Return ONLY the JSON object, no prose."
        )
        try:
            r = await self._client.post(
                f"{self._base}/api/generate",
                json={
                    "model": self._model,
                    "prompt": full_prompt,
                    "stream": False,
                    "format": "json",
                    "options": {"num_predict": max_tokens},
                },
            )
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"ollama structured failed: {exc}") from exc

        data = r.json()
        raw_text = data.get("response", "{}")
        try:
            value = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise LLMProviderError(
                f"ollama structured response not valid JSON: {raw_text!r}",
                kind="schema_validation",
            ) from exc

        return StructuredResult(
            text=raw_text,
            value=value,
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
            model=self._model,
        )

    async def stream(
        self,
        prompt: str,
        *,
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        try:
            async with self._client.stream(
                "POST",
                f"{self._base}/api/generate",
                json={
                    "model": self._model,
                    "prompt": prompt,
                    "stream": True,
                    "options": {"num_predict": max_tokens},
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    payload = json.loads(line)
                    if payload.get("done"):
                        return
                    text = payload.get("response", "")
                    if text:
                        yield text
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"ollama stream failed: {exc}") from exc

    async def embed(self, text: str) -> EmbeddingResult:
        try:
            r = await self._client.post(
                f"{self._base}/api/embeddings",
                json={"model": _EMBEDDING_MODEL, "prompt": text},
            )
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"ollama embed failed: {exc}") from exc

        data = r.json()
        if "embedding" not in data or not isinstance(data["embedding"], list):
            raise LLMProviderError(
                f"ollama embed response missing embedding: {data!r}",
                kind="schema_validation",
            )
        vector = data["embedding"]
        return EmbeddingResult(
            vector=[float(v) for v in vector],
            input_tokens=int(data.get("prompt_eval_count", 0)),
            output_tokens=0,
            model=_EMBEDDING_MODEL,
        )

    def estimate_cost(self, *, input_tokens: int, output_tokens: int) -> float:
        return 0.0  # local = free
