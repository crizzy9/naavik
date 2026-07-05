"""3-agent voting council for bullet selection — plan 67 (0.3.4) § C.2 / T3.

Submits 3 heterogeneous-persona prompts via Anthropic batch API (50%
cost discount per OQ-2). Merges rankings via Borda count with
deterministic tie-break (lower bullet_id wins). Falls back to
synchronous `asyncio.gather` when the batch API is unavailable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from llm import get_provider
from llm.anthropic import AnthropicProvider, BatchRequest
from llm.prompts.council_personas import PERSONAS, PROMPT_BUILDERS, CouncilVote
from services import llm_tracker  # noqa: F401  (preserved for test monkeypatch path)
from services._council_common import run_persona_batch, sync_fallback
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


# Plan 75 / 0.3.3.11 — `_sync_fallback` body moved to `services._council_common`
# so the cross-module use (critique_council also calls it) is explicit. Kept as
# a module-local alias for back-compat with any direct callers / tests pinning
# the private name.
_sync_fallback = sync_fallback


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

    # isinstance stays evaluated HERE (tests patch services.council.isinstance
    # to force the branch); _persist_apiusage is passed by module-global so the
    # services.council._persist_apiusage patch seam keeps intercepting.
    responses, batch_used = await run_persona_batch(
        session=session,
        user_id=user_id,
        application_id=application_id,
        provider=provider,
        requests=requests,
        system=system,
        cache_system=cache_system,
        prompt_prefix="council",
        use_batch=isinstance(provider, AnthropicProvider),
        persist_usage=_persist_apiusage,
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
