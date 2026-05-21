"""3-agent voting council for bullet selection — plan 67 (0.3.4) § C.2 / T3.

Submits 3 heterogeneous-persona prompts via Anthropic batch API (50%
cost discount per OQ-2). Merges rankings via Borda count with
deterministic tie-break (lower bullet_id wins). Falls back to
synchronous `asyncio.gather` when the batch API is unavailable.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from llm import get_provider
from llm.anthropic import AnthropicProvider, BatchRequest, BatchResponse
from llm.base import LLMProviderError
from llm.prompts.council_personas import PERSONAS, PROMPT_BUILDERS, CouncilVote
from services import llm_tracker
from services.llm_tracker import _persist_usage as _persist_apiusage

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from models import Settings

log = logging.getLogger(__name__)


@dataclass(slots=True)
class SelectedBullets:
    """Council-merged bullet selection output."""

    selected_ids: list[int] = field(default_factory=list)
    persona_rankings: dict[str, list[int]] = field(default_factory=dict)
    borda_scores: dict[int, int] = field(default_factory=dict)
    batch_used: bool = True
    degraded_reason: str | None = None


def _borda_merge(
    persona_rankings: dict[str, list[int]],
    candidate_ids: set[int],
    *,
    top_k: int,
) -> tuple[list[int], dict[int, int]]:
    """Aggregate persona rankings via Borda count.

    Each persona's `ranked_bullet_ids` awards `N - rank` points to each
    bullet (N = total candidates; rank 0 = best). Unranked bullets receive
    0 points from that persona. Final selection = top-K by Borda score
    desc; ties broken by lower bullet_id (deterministic per T3).
    """
    n = len(candidate_ids)
    scores: dict[int, int] = dict.fromkeys(candidate_ids, 0)
    for ranking in persona_rankings.values():
        seen_in_persona: set[int] = set()
        for rank, bid in enumerate(ranking):
            if bid not in candidate_ids or bid in seen_in_persona:
                continue
            seen_in_persona.add(bid)
            scores[bid] += max(n - rank, 0)
    # Sort by score DESC, then bullet_id ASC for deterministic ties.
    ordered = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    selected = [bid for bid, _ in ordered[:top_k]]
    return selected, scores


async def _sync_fallback(
    *,
    session: AsyncSession | None,
    user_id: int,
    application_id: int | None,
    provider,
    requests: list[BatchRequest],
    system: str | None,
    cache_system: bool,
) -> list[BatchResponse]:
    """Submit 3 personas sequentially via `provider.structured`.

    Loses the 50% batch discount but keeps the council shape working when
    batch API returns 503 or polling times out. Uses
    `asyncio.gather` so the 3 calls go in parallel inside the asyncio loop
    even though each persona is its own tracked_call invocation.
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


async def vote_on_bullet_selection(
    candidate_bullets: list[dict],
    job: dict,
    *,
    session: AsyncSession | None,
    user_id: int,
    settings: Settings,
    application_id: int | None = None,
    system: str | None = None,
    cache_system: bool = False,
    top_k: int = 8,
    max_tokens_per_persona: int = 1200,
) -> SelectedBullets:
    """Run the 3-persona bullet-selection council.

    `candidate_bullets` is a list of `{"id": int, "text": str}` dicts (the
    user's `auto`-class bullets, post-override filter). `job` is the JD
    snippet dict carrying `role` / `description` / `skills_required` /
    `company`. `top_k` defaults to 8 — matches the existing FREE-pipeline
    `select_bullets` count post-trim.

    Returns `SelectedBullets` with the merged selection + per-persona
    rankings + Borda scores for audit-trail surfacing.
    """
    candidate_ids = {b["id"] for b in candidate_bullets}
    if not candidate_ids:
        return SelectedBullets(batch_used=False)

    provider = get_provider(settings)
    requests = [
        BatchRequest(
            custom_id=persona,
            prompt=PROMPT_BUILDERS[persona](candidate_bullets, job),
            schema=CouncilVote,
            max_tokens=max_tokens_per_persona,
            system=system,
            cache_system=cache_system,
        )
        for persona in PERSONAS
    ]

    batch_used = False
    responses: list[BatchResponse]
    if isinstance(provider, AnthropicProvider):
        try:
            responses = await provider.batch(requests)
            batch_used = True
            # Anthropic batch API returns per-request usage; record one
            # ApiUsage row per persona at half rate.
            for resp in responses:
                cost = (
                    provider.estimate_cost(
                        input_tokens=resp.input_tokens,
                        output_tokens=resp.output_tokens,
                    )
                    * 0.5
                )  # 50% batch discount
                await _persist_apiusage(
                    session,
                    user_id=user_id,
                    provider=provider,
                    method="structured",
                    prompt_name=f"council_{resp.custom_id}_batch",
                    application_id=application_id,
                    input_tokens=resp.input_tokens,
                    output_tokens=resp.output_tokens,
                    cost_usd=cost,
                    latency_ms=0,
                    succeeded=resp.succeeded,
                    error_kind=None if resp.succeeded else "batch_request_failed",
                )
        except LLMProviderError as exc:
            log.info("batch API unavailable, falling back to sync gather: %s", exc)
            responses = await _sync_fallback(
                session=session,
                user_id=user_id,
                application_id=application_id,
                provider=provider,
                requests=requests,
                system=system,
                cache_system=cache_system,
            )
    else:
        responses = await _sync_fallback(
            session=session,
            user_id=user_id,
            application_id=application_id,
            provider=provider,
            requests=requests,
            system=system,
            cache_system=cache_system,
        )

    persona_rankings: dict[str, list[int]] = {}
    for resp in responses:
        if not resp.succeeded:
            persona_rankings[resp.custom_id] = []
            continue
        raw_ranked = resp.value.get("ranked_bullet_ids") or []
        cleaned: list[int] = []
        for entry in raw_ranked:
            try:
                bid = int(entry)
            except (TypeError, ValueError):
                continue
            if bid in candidate_ids:
                cleaned.append(bid)
        persona_rankings[resp.custom_id] = cleaned

    # If every persona failed, return empty selection — caller falls back
    # to FREE-tier select_bullets via degraded_mode.
    successes = sum(1 for r in responses if r.succeeded and persona_rankings.get(r.custom_id))
    if successes == 0:
        return SelectedBullets(
            persona_rankings=persona_rankings,
            batch_used=batch_used,
            degraded_reason="all_personas_failed",
        )

    selected, scores = _borda_merge(persona_rankings, candidate_ids, top_k=top_k)
    return SelectedBullets(
        selected_ids=selected,
        persona_rankings=persona_rankings,
        borda_scores=scores,
        batch_used=batch_used,
    )
