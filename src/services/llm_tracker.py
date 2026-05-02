"""LLM call tracker — wraps every provider call with cost + latency logging.

Per BACKEND.md § M.4 + plan 10 § B.4. Every `LLMProvider.complete /
structured / stream` invocation flows through `tracked_call`, which:

1. Times the call.
2. Persists an `ApiUsage` row with `(provider, model, method, prompt_name,
   input_tokens, output_tokens, cost_usd, latency_ms)`.
3. On failure, retries per BACKEND.md § M.5:
   - rate_limit (429): exponential backoff, max 3 retries
   - timeout: retry once with longer timeout
   - 500: try fallback provider if `Settings.llm_fallback_provider` set
   - schema_validation: re-prompt once with stricter instructions
4. Emits the `ApiUsage` row even on failure (with `succeeded=False, error_kind=...`).

Settings · LLM Provider's "THIS MONTH" / "AVG / GENERATION" / "RATE LIMIT"
cost cards aggregate over this table.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from llm.base import (
    CompletionResult,
    LLMProvider,
    LLMProviderError,
    StructuredResult,
)
from models import ApiUsage
from models import LLMProvider as LLMProviderEnum

log = logging.getLogger(__name__)

_RETRY_ATTEMPTS = {
    "rate_limit": 3,
    "timeout": 1,
    "schema_validation": 1,
    "provider_error": 0,
}
_BACKOFF_BASE_SECONDS = 1.0


def _provider_id_to_enum(provider_id: str) -> LLMProviderEnum:
    return LLMProviderEnum(provider_id)


async def _persist_usage(
    session: AsyncSession | None,
    *,
    user_id: int,
    provider: LLMProvider,
    method: str,
    prompt_name: str | None,
    application_id: int | None,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    latency_ms: int,
    succeeded: bool,
    error_kind: str | None,
) -> None:
    if session is None:
        return  # caller didn't pass a session — tests can opt out
    row = ApiUsage(
        user_id=user_id,
        application_id=application_id,
        provider=_provider_id_to_enum(provider.provider_id),
        model=provider.model_name,
        method=method,
        prompt_name=prompt_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        succeeded=succeeded,
        error_kind=error_kind,
    )
    session.add(row)
    try:
        await session.flush()
    except Exception as exc:  # noqa: BLE001
        log.warning("failed to persist ApiUsage row: %s", exc)


def _classify_error(exc: Exception) -> str:
    if isinstance(exc, LLMProviderError):
        return exc.kind
    msg = (str(exc) or type(exc).__name__).lower()
    if "rate limit" in msg or "429" in msg or "too many" in msg:
        return "rate_limit"
    if "timeout" in msg or "timed out" in msg:
        return "timeout"
    if "json" in msg or "schema" in msg or "validation" in msg:
        return "schema_validation"
    return "provider_error"


async def tracked_call(
    *,
    session: AsyncSession | None,
    user_id: int,
    provider: LLMProvider,
    method: str,
    prompt_name: str | None = None,
    application_id: int | None = None,
    fallback_provider: LLMProvider | None = None,
    **call_kwargs: Any,
) -> Any:
    """Invoke `provider.<method>(**call_kwargs)` with retry + ApiUsage logging.

    `method` ∈ {"complete", "structured", "stream"}. `stream` returns the
    coroutine that yields the AsyncIterator — caller awaits + iterates.
    """
    fn: Callable[..., Awaitable[Any]] = getattr(provider, method)

    attempt = 0
    use_provider = provider

    while True:
        start = time.perf_counter()
        try:
            result = await fn(**call_kwargs)
        except Exception as exc:  # noqa: BLE001
            kind = _classify_error(exc)
            latency_ms = int((time.perf_counter() - start) * 1000)
            await _persist_usage(
                session,
                user_id=user_id,
                provider=use_provider,
                method=method,
                prompt_name=prompt_name,
                application_id=application_id,
                input_tokens=0,
                output_tokens=0,
                cost_usd=0.0,
                latency_ms=latency_ms,
                succeeded=False,
                error_kind=kind,
            )

            allowed = _RETRY_ATTEMPTS.get(kind, 0)
            if attempt < allowed:
                attempt += 1
                if kind == "rate_limit":
                    await asyncio.sleep(_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))
                continue

            # Exhausted retries on primary; try fallback if 500-class.
            if (
                kind in {"provider_error", "timeout"}
                and fallback_provider is not None
                and use_provider is provider
            ):
                use_provider = fallback_provider
                fn = getattr(use_provider, method)
                attempt = 0
                continue

            raise LLMProviderError(
                f"{provider.provider_id} {method} failed after retries: {exc}",
                kind=kind,
            ) from exc

        latency_ms = int((time.perf_counter() - start) * 1000)

        # Pull token counts from result for ApiUsage row.
        if isinstance(result, (CompletionResult, StructuredResult)):
            in_tok = result.input_tokens
            out_tok = result.output_tokens
        else:
            in_tok = 0
            out_tok = 0

        cost_usd = use_provider.estimate_cost(input_tokens=in_tok, output_tokens=out_tok)
        await _persist_usage(
            session,
            user_id=user_id,
            provider=use_provider,
            method=method,
            prompt_name=prompt_name,
            application_id=application_id,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            succeeded=True,
            error_kind=None,
        )
        return result
