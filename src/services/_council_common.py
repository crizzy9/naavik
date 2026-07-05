"""Shared helpers for council.py + critique_council.py — plan 75 / 0.3.3.11.

The `sync_fallback` helper was a private symbol on `services.council` and
`services.critique_council` reached across modules via `_sync_fallback`
(private-API import). Per hacker PR #168 LOW-4: factor the helper into a
deliberately-shared module so the cross-module contract is explicit.

No behavior change — the body is lifted verbatim from `council._sync_fallback`.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from llm.anthropic import BatchRequest, BatchResponse
from llm.base import LLMProviderError
from services import llm_tracker

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

log = logging.getLogger(__name__)


async def sync_fallback(
    *,
    session: AsyncSession | None,
    user_id: int,
    application_id: int | None,
    provider,
    requests: list[BatchRequest],
    system: str | None,
    cache_system: bool,
    prompt_prefix: str = "council",
) -> list[BatchResponse]:
    """Submit N persona requests sequentially via `provider.structured`.

    Loses the 50% batch discount but keeps the council shape working when
    the batch API returns 503 or polling times out. Uses `asyncio.gather`
    so the calls go in parallel inside the asyncio loop even though each
    persona is its own tracked_call invocation.

    Called by both `services.council.vote_on_bullet_selection` (T3 voting
    council) and `services.critique_council.collect_critiques` (T4 critique
    council). Plan 75 / 0.3.3.11 — moved from `services.council` to this
    shared module so the cross-import is explicit.

    `prompt_prefix` (plan 91 5.1): usage rows are labelled
    `{prompt_prefix}_{persona}` so `settings_service._PREMIUM_STAGE_PROMPTS`
    buckets them correctly. The old hardcoded `council_` prefix mislabelled
    critique-council sync-fallback rows as `council_*`, dropping them out of
    the `critique_usd` cost projection entirely.
    """

    async def _one(req: BatchRequest) -> BatchResponse:
        try:
            result = await llm_tracker.tracked_call(
                session=session,
                user_id=user_id,
                provider=provider,
                method="structured",
                prompt_name=f"{prompt_prefix}_{req.custom_id}",
                application_id=application_id,
                prompt=req.prompt,
                schema=req.schema,
                max_tokens=req.max_tokens,
                system=system,
                cache_system=cache_system,
            )
            return BatchResponse(
                custom_id=req.custom_id,
                value=getattr(result, "value", {}) or {},
                text=getattr(result, "text", "") or "",
                input_tokens=int(getattr(result, "input_tokens", 0) or 0),
                output_tokens=int(getattr(result, "output_tokens", 0) or 0),
                succeeded=True,
            )
        except LLMProviderError as exc:
            log.warning("council sync fallback failed for %s: %s", req.custom_id, exc)
            return BatchResponse(custom_id=req.custom_id, succeeded=False, error=str(exc))

    return list(await asyncio.gather(*(_one(req) for req in requests)))


async def run_persona_batch(
    *,
    session: AsyncSession | None,
    user_id: int,
    application_id: int | None,
    provider,
    requests: list[BatchRequest],
    system: str | None,
    cache_system: bool,
    prompt_prefix: str,
    use_batch: bool,
    persist_usage,
) -> tuple[list[BatchResponse], bool]:
    """Batch-or-sync persona dispatch shared by both councils (plan 91 5.1).

    When `use_batch` is True, submit via the Anthropic batch API (50% cost
    discount) and record one usage row per persona through `persist_usage`
    (passed in so each council module keeps its own patchable
    `_persist_apiusage` seam); on `LLMProviderError` — or when `use_batch`
    is False — fall back to `sync_fallback`. Returns
    `(responses, batch_used)`.
    """
    if use_batch:
        try:
            responses = await provider.batch(requests)
            for resp in responses:
                cost = (
                    provider.estimate_cost(
                        input_tokens=resp.input_tokens,
                        output_tokens=resp.output_tokens,
                    )
                    * 0.5
                )  # 50% batch discount
                await persist_usage(
                    session,
                    user_id=user_id,
                    provider=provider,
                    method="structured",
                    prompt_name=f"{prompt_prefix}_{resp.custom_id}_batch",
                    application_id=application_id,
                    input_tokens=resp.input_tokens,
                    output_tokens=resp.output_tokens,
                    cost_usd=cost,
                    latency_ms=0,
                    succeeded=resp.succeeded,
                    error_kind=None if resp.succeeded else "batch_request_failed",
                )
            return responses, True
        except LLMProviderError as exc:
            log.info("%s batch unavailable; falling back to sync: %s", prompt_prefix, exc)
    responses = await sync_fallback(
        session=session,
        user_id=user_id,
        application_id=application_id,
        provider=provider,
        requests=requests,
        system=system,
        cache_system=cache_system,
        prompt_prefix=prompt_prefix,
    )
    return responses, False
