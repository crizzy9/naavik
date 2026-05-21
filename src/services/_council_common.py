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
    """

    async def _one(req: BatchRequest) -> BatchResponse:
        try:
            result = await llm_tracker.tracked_call(
                session=session,
                user_id=user_id,
                provider=provider,
                method="structured",
                prompt_name=f"council_{req.custom_id}",
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
