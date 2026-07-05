"""Multi-persona recruiter critique council — plan 67 (0.3.4) § C.3 / T4.

Submits 3 persona reviewers via Anthropic batch API. Aggregates verdicts:
- Consensus concerns via `difflib.SequenceMatcher.ratio() >= 0.6` —
  similar phrasing across personas merges into one signal
- Majority recommendation tally (ship / revise / reject)
- When majority votes "revise" -> caller MAY trigger ONE regeneration
  pass embedding `consensus_concerns` into the constitution preamble's
  `extra_constraints` slot (hard cap at 1 regen per bundle per T4)
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

from llm import get_provider
from llm.anthropic import AnthropicProvider, BatchRequest
from llm.prompts.critique_personas import PERSONAS, PROMPT_BUILDERS, CritiqueVote
from services._council_common import run_persona_batch
from services.llm_tracker import _persist_usage as _persist_apiusage

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from models import Settings

log = logging.getLogger(__name__)

CONSENSUS_SIMILARITY_THRESHOLD = 0.6


@dataclass(slots=True)
class CritiqueReport:
    """Aggregated critique-council verdict."""

    persona_votes: list[dict] = field(default_factory=list)
    consensus_concerns: list[str] = field(default_factory=list)
    disagreement_items: list[str] = field(default_factory=list)
    recommendation_tally: dict[str, int] = field(default_factory=dict)
    majority_recommendation: str = "ship"
    should_regenerate: bool = False
    batch_used: bool = True
    degraded_reason: str | None = None


def _cluster_concerns(votes: list[dict]) -> tuple[list[str], list[str]]:
    """Group similar concerns across persona votes.

    Returns `(consensus, disagreement)`:
      - consensus  — concerns appearing in >= 2/3 of personas (similarity
                     >= CONSENSUS_SIMILARITY_THRESHOLD). One representative
                     phrase per cluster (the longest, as it carries more signal).
      - disagreement — concerns appearing in only one persona.
    """
    # Flatten with persona attribution
    items: list[tuple[str, str]] = []  # (persona, concern)
    for vote in votes:
        persona = vote.get("persona", "")
        for concern in vote.get("concerns", []) or []:
            concern_str = str(concern).strip()
            if concern_str:
                items.append((persona, concern_str))
    if not items:
        return [], []

    # Cluster via greedy similarity
    clusters: list[list[tuple[str, str]]] = []
    for persona, concern in items:
        placed = False
        for cluster in clusters:
            representative = cluster[0][1]
            ratio = SequenceMatcher(None, concern.lower(), representative.lower()).ratio()
            if ratio >= CONSENSUS_SIMILARITY_THRESHOLD:
                cluster.append((persona, concern))
                placed = True
                break
        if not placed:
            clusters.append([(persona, concern)])

    consensus: list[str] = []
    disagreement: list[str] = []
    for cluster in clusters:
        distinct_personas = {persona for persona, _ in cluster}
        if len(distinct_personas) >= 2:
            # Pick the longest phrase as representative
            rep = max((c for _, c in cluster), key=len)
            consensus.append(rep)
        else:
            disagreement.append(cluster[0][1])
    return consensus, disagreement


def _majority_recommendation(votes: list[dict]) -> tuple[str, dict[str, int]]:
    """Return (majority, tally). Majority breaks ties to 'ship' (safest)."""
    counter: Counter[str] = Counter()
    for vote in votes:
        rec = vote.get("recommendation", "ship")
        if rec in ("ship", "revise", "reject"):
            counter[rec] += 1
    tally = {"ship": counter["ship"], "revise": counter["revise"], "reject": counter["reject"]}
    if not counter:
        return "ship", tally
    top = counter.most_common(1)[0]
    top_rec, top_count = top
    # Tie → ship (favor shipping by default)
    if list(counter.values()).count(top_count) > 1:
        return "ship", tally
    return top_rec, tally


async def critique_bundle(
    resume_text: str,
    cover_letter_text: str,
    job_desc: str,
    *,
    session: AsyncSession | None,
    user_id: int,
    settings: Settings,
    application_id: int | None = None,
    system: str | None = None,
    cache_system: bool = False,
    max_tokens_per_persona: int = 1200,
) -> CritiqueReport:
    """Submit 3 critique-council prompts; aggregate into a CritiqueReport.

    Caller decides whether to act on `should_regenerate` — this function
    just surfaces the signal. T4 caps regeneration at 1 pass per bundle;
    enforcement lives in the bundle_generator orchestrator (Wave 6).
    """
    provider = get_provider(settings)
    requests = [
        BatchRequest(
            custom_id=persona,
            prompt=PROMPT_BUILDERS[persona](resume_text, cover_letter_text, job_desc),
            schema=CritiqueVote,
            max_tokens=max_tokens_per_persona,
            system=system,
            cache_system=cache_system,
        )
        for persona in PERSONAS
    ]

    # isinstance stays evaluated HERE (tests patch
    # services.critique_council.isinstance to force the branch);
    # _persist_apiusage passes the module-global patch seam through.
    # prompt_prefix="critique" is the plan 91 5.1 bug fix: sync-fallback
    # rows were mislabelled council_* and fell out of the critique_usd
    # cost-projection bucket.
    responses, batch_used = await run_persona_batch(
        session=session,
        user_id=user_id,
        application_id=application_id,
        provider=provider,
        requests=requests,
        system=system,
        cache_system=cache_system,
        prompt_prefix="critique",
        use_batch=isinstance(provider, AnthropicProvider),
        persist_usage=_persist_apiusage,
    )

    persona_votes: list[dict] = []
    for resp in responses:
        if not resp.succeeded:
            persona_votes.append(
                {
                    "persona": resp.custom_id,
                    "strengths": [],
                    "concerns": [],
                    "recommendation": "ship",
                    "specific_changes": [],
                }
            )
            continue
        persona_votes.append(
            {
                "persona": resp.value.get("persona", resp.custom_id),
                "strengths": list(resp.value.get("strengths") or []),
                "concerns": list(resp.value.get("concerns") or []),
                "recommendation": str(resp.value.get("recommendation") or "ship"),
                "specific_changes": list(resp.value.get("specific_changes") or []),
            }
        )

    successes = sum(1 for r in responses if r.succeeded)
    if successes == 0:
        return CritiqueReport(
            persona_votes=persona_votes,
            batch_used=batch_used,
            degraded_reason="all_personas_failed",
        )

    consensus, disagreement = _cluster_concerns(persona_votes)
    majority_rec, tally = _majority_recommendation(persona_votes)
    revise_votes = tally.get("revise", 0)
    # Majority revise = >= 2/3 personas (when all 3 returned). Use successes
    # as denominator so a single missing persona doesn't dilute the trigger.
    should_regen = revise_votes >= 2 and revise_votes > tally.get("ship", 0)

    return CritiqueReport(
        persona_votes=persona_votes,
        consensus_concerns=consensus,
        disagreement_items=disagreement,
        recommendation_tally=tally,
        majority_recommendation=majority_rec,
        should_regenerate=should_regen,
        batch_used=batch_used,
    )
