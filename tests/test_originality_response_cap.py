"""Originality.ai response-size cap regression — PR #168 round-2 hacker MED-2.

A compromised/MitM'd `api.originality.ai` could stream an arbitrarily large
body and exhaust the FastAPI worker's memory (the detector loop runs inside
the PREMIUM bundle render path, synchronously from the user's click).

`OriginalityProvider.score_text` now streams the response with a 64 KiB
hard cap. Oversized bodies return None + a warning log; legitimate small
bodies still parse cleanly.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from llm.providers.originality import (
    MAX_RESPONSE_BYTES,
    OriginalityProvider,
)


class _FakeStreamResponse:
    """Mimics `httpx.Response` as returned from `client.stream(...)`."""

    def __init__(self, status_code: int, chunks: list[bytes]) -> None:
        self.status_code = status_code
        self._chunks = chunks

    async def aiter_bytes(self, chunk_size: int = 8192):
        for chunk in self._chunks:
            yield chunk

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None


class _FakeClient:
    """Mimics `httpx.AsyncClient` to feed canned chunks back."""

    def __init__(self, status_code: int, chunks: list[bytes]) -> None:
        self._response = _FakeStreamResponse(status_code, chunks)

    def stream(self, method: str, url: str, **kwargs):
        return self._response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None


@pytest.mark.asyncio
async def test_score_text_handles_small_response(monkeypatch):
    """Normal sub-KiB response parses cleanly and surfaces the ai score."""
    import llm.providers.originality as orig

    body = b'{"score": {"ai": 0.87, "original": 0.13}}'
    fake = _FakeClient(200, [body])
    monkeypatch.setattr(orig.httpx, "AsyncClient", MagicMock(return_value=fake))

    provider = OriginalityProvider("sk-test")
    score = await provider.score_text("some text to scan")
    assert score == pytest.approx(0.87)


@pytest.mark.asyncio
async def test_score_text_rejects_oversized_response(monkeypatch):
    """Streamed body exceeding MAX_RESPONSE_BYTES triggers graceful None
    return — no memory exhaustion vector."""
    import llm.providers.originality as orig

    # 70 KiB > 64 KiB cap; stream in 8KiB chunks to mimic real flow
    oversized_chunks = [b"a" * 8192 for _ in range(9)]
    total_size = sum(len(c) for c in oversized_chunks)
    assert total_size > MAX_RESPONSE_BYTES, "fixture must exceed cap"

    fake = _FakeClient(200, oversized_chunks)
    monkeypatch.setattr(orig.httpx, "AsyncClient", MagicMock(return_value=fake))

    provider = OriginalityProvider("sk-test")
    score = await provider.score_text("anything")
    assert score is None


@pytest.mark.asyncio
async def test_score_text_handles_non_200(monkeypatch):
    """Non-200 status with bounded body length doesn't blow memory."""
    import llm.providers.originality as orig

    fake = _FakeClient(503, [b"upstream down"])
    monkeypatch.setattr(orig.httpx, "AsyncClient", MagicMock(return_value=fake))

    provider = OriginalityProvider("sk-test")
    score = await provider.score_text("text")
    assert score is None


@pytest.mark.asyncio
async def test_score_text_handles_malformed_json(monkeypatch):
    """Non-JSON body returns None; no exception escapes the provider."""
    import llm.providers.originality as orig

    fake = _FakeClient(200, [b"not valid json"])
    monkeypatch.setattr(orig.httpx, "AsyncClient", MagicMock(return_value=fake))

    provider = OriginalityProvider("sk-test")
    score = await provider.score_text("text")
    assert score is None


@pytest.mark.asyncio
async def test_score_text_no_op_when_unconfigured(monkeypatch):
    """Empty api_key short-circuits without making any HTTP request."""
    import llm.providers.originality as orig

    sentinel = MagicMock()
    monkeypatch.setattr(orig.httpx, "AsyncClient", sentinel)

    provider = OriginalityProvider(None)
    score = await provider.score_text("text")
    assert score is None
    sentinel.assert_not_called()
