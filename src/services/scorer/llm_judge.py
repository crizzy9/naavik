"""Layer 4 — LLM-as-judge (plan 65 § D.5 + § T1 + § T6).

The judge is invoked only when the layer-1 + layer-2 composite clears
`_LLM_GATE`. The orchestrator runs a per-job cost-cap probe (T1) before
firing; this module exposes both the probe + the call. Returns
`(JobScore | None, skip_reason)` so the orchestrator can persist the
right `judge_skipped_reason` in `Job.match_breakdown`.

All LLM calls flow through `llm_tracker.tracked_call` so `ApiUsage` rows
persist (per `engineer-llm-tracker-wrap` skill).
"""

from __future__ import annotations

import logging

from sqlmodel.ext.asyncio.session import AsyncSession

from llm import LLMProviderError, get_provider
from llm.prompts.score_job import PROMPT, JobScore
from models import Bullet, Job, Profile, Settings
from models.enums import Tag
from services import llm_tracker

from . import _ESTIMATED_JUDGE_COST_USD

log = logging.getLogger(__name__)


async def cost_cap_exhausted(
    session: AsyncSession,
    *,
    user_id: int,
    settings: Settings,
) -> bool:
    """True iff a layer-4 call would exceed the daily cap (plan 65 § T1).

    Pre-flight probe — runs before each per-job LLM dispatch. The estimate
    is conservative (`_ESTIMATED_JUDGE_COST_USD = 0.015`); over-blocking
    one borderline job beats overshooting the cap.

    Plan 86 / 0.4.5.01 + R5 round 2 — thin wrapper around
    `llm_tracker.acquire_cost_cap_slot`. Acquires + immediately releases
    the placeholder slot for "check-only" callers (existing scorer
    orchestrator path that runs the probe, then dispatches
    `_llm_judge_score` separately). Direct callers wanting the real
    placeholder-row protection should use `acquire_cost_cap_slot` +
    `release_cost_cap_slot` directly so the placeholder holds the slot
    across the LLM call window.
    """
    slot_id = await llm_tracker.acquire_cost_cap_slot(
        session,
        user_id=user_id,
        estimated_cost_usd=_ESTIMATED_JUDGE_COST_USD,
        cap_usd=settings.daily_llm_cost_cap_usd,
    )
    if slot_id is None:
        return True
    await llm_tracker.release_cost_cap_slot(session, slot_id)
    return False


def _compose_profile_summary(profile: Profile) -> str:
    """One-block render of profile identity + summary for the prompt."""
    return "\n".join(
        x
        for x in (
            profile.full_name,
            profile.headline,
            profile.summary_short or profile.summary_full or "",
        )
        if x
    )


def _render_profile_tags(profile: Profile, bullets: list[Bullet]) -> str:
    """Union of bullet tags across the candidate bullets passed to the prompt."""
    seen: set[str] = set()
    for b in bullets or []:
        for t in b.tags or []:
            seen.add(t)
    return ", ".join(sorted(seen))


def _render_bullets_with_ids(bullets: list[Bullet]) -> str:
    """One bullet per line: `[id] text` (truncate to 200 chars)."""
    return "\n".join(
        f"[{b.id}] {(b.text or '')[:200]}" for b in (bullets or []) if b.id is not None
    )


async def _llm_judge_score(
    session: AsyncSession,
    *,
    user_id: int,
    job: Job,
    profile: Profile,
    candidate_bullets: list[Bullet],
    tag_score: float,
    semantic_score: float | None,
    settings: Settings,
) -> tuple[JobScore | None, str | None]:
    """Call the LLM judge (plan 65 § D.5).

    Returns:
        `(JobScore, None)` on success.
        `(None, "no_provider")` when no LLM provider is configured (OQ-2).
        `(None, "llm_failed")` on LLMProviderError after retries.
    """
    try:
        provider = get_provider(settings)
    except LLMProviderError as exc:
        log.info("score_job no provider configured: %s", exc)
        return None, "no_provider"
    if provider is None:
        return None, "no_provider"

    rendered = PROMPT.format(
        profile=_compose_profile_summary(profile),
        profile_tags=_render_profile_tags(profile, candidate_bullets),
        candidate_bullets=_render_bullets_with_ids(candidate_bullets),
        company=job.company or "",
        role=job.role or "",
        description=(job.description or "")[:4000],
        job_tags=", ".join(job.tags or []),
        skills=", ".join(job.skills_required or []),
        visa_restrictions=str(job.visa_restrictions or "none"),
        tag_score=tag_score,
        semantic_score=semantic_score if semantic_score is not None else 0.0,
        tag_vocabulary=", ".join(t.value for t in Tag),
    )
    try:
        result = await llm_tracker.tracked_call(
            session=session,
            user_id=user_id,
            provider=provider,
            method="structured",
            prompt_name="score_job",
            prompt=rendered,
            schema=JobScore,
        )
    except LLMProviderError as exc:
        log.warning("score_job LLM failed for job %s: %s", job.id, exc)
        return None, "llm_failed"

    raw = getattr(result, "value", result)
    try:
        score = JobScore.model_validate(raw)
    except Exception as exc:  # noqa: BLE001
        log.warning("score_job validation failed for job %s: %s", job.id, exc)
        return None, "llm_failed"
    return score, None


__all__ = [
    "_compose_profile_summary",
    "_llm_judge_score",
    "_render_bullets_with_ids",
    "_render_profile_tags",
    "cost_cap_exhausted",
]
