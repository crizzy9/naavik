"""Adversarial Claude-as-detector loop — plan 67 (0.3.4) § C.1 / T1.

Iterates Claude-as-detector + phrase-targeted refine until the AI-confidence
drops below a target threshold OR a hard iteration cap is reached. At
convergence (or final iter) optionally consults Originality.ai for a
real-detector spot-check (hybrid per locked OQ-4).

Budget-aware: probes `generation.is_cost_capped` between iterations
and exits early when today's spend approaches the daily cap. Honors locked
OQ-3 (max_iters cap N=3 with budget-aware early exit).

All inner Claude calls wrap `services.llm_tracker.tracked_call` so cost +
latency persist to ApiUsage.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from llm import get_provider
from llm.base import LLMProviderError
from llm.prompts.detect_ai_likelihood import DetectorVerdict
from llm.prompts.detect_ai_likelihood import build_prompt as build_detect_prompt
from llm.prompts.refine_to_human import RefinedText
from llm.prompts.refine_to_human import build_prompt as build_refine_prompt
from llm.providers.originality import score_text as originality_score_text
from services import generation as dg
from services import llm_tracker

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from models import Settings

log = logging.getLogger(__name__)

DEFAULT_TARGET_CONFIDENCE = 0.25
DEFAULT_MAX_ITERS = 3


@dataclass(slots=True)
class DetectorIteration:
    """One pass through the detector + (optional) refine cycle."""

    iter_n: int
    confidence: float
    flagged_phrases: list[str] = field(default_factory=list)
    refinements: list[str] = field(default_factory=list)
    rationale: str = ""


@dataclass(slots=True)
class DetectorReport:
    """End-state of `run_detector_loop`. `originality_score` is None when
    no API key is configured OR the loop converged at iter 0 (no refine
    happened — nothing to ground-truth check)."""

    final_text: str
    final_confidence: float
    target_met: bool
    iterations: list[DetectorIteration] = field(default_factory=list)
    originality_score: float | None = None
    early_exit_reason: str | None = None


async def run_detector_loop(
    text: str,
    *,
    session: AsyncSession | None,
    user_id: int,
    settings: Settings,
    application_id: int | None = None,
    system: str | None = None,
    cache_system: bool = False,
    max_iters: int = DEFAULT_MAX_ITERS,
    target_confidence: float = DEFAULT_TARGET_CONFIDENCE,
) -> DetectorReport:
    """Iterate Claude-as-detector + refine until convergence or cap.

    Returns a `DetectorReport` carrying the final text + per-iter audit
    trail. When `Settings.originality_api_key` is set AND at least one
    refine pass executed, calls Originality.ai once at convergence and
    records the ground-truth `ai_score`.
    """
    iterations: list[DetectorIteration] = []
    current_text = text
    final_confidence = 1.0
    target_met = False
    early_exit: str | None = None

    if not text:
        return DetectorReport(
            final_text="",
            final_confidence=0.0,
            target_met=True,
            iterations=[],
            originality_score=None,
            early_exit_reason="empty_input",
        )

    provider = get_provider(settings)
    refined_count = 0

    for iter_n in range(max_iters):
        # Budget probe between iterations (also fires before iter 0 so a
        # call into a fully-capped account exits without any LLM spend).
        if session is not None and await dg.is_cost_capped(session, user_id, settings):
            early_exit = "cost_cap_reached"
            break

        try:
            detect_result = await llm_tracker.tracked_call(
                session=session,
                user_id=user_id,
                provider=provider,
                method="structured",
                prompt_name="detect_ai_likelihood",
                application_id=application_id,
                prompt=build_detect_prompt(current_text),
                schema=DetectorVerdict,
                system=system,
                cache_system=cache_system,
            )
        except LLMProviderError as exc:
            log.warning("detect_ai_likelihood failed at iter %d: %s", iter_n, exc)
            early_exit = "detector_provider_error"
            break

        verdict_dict = detect_result.value or {}
        confidence = float(verdict_dict.get("ai_confidence") or 0.0)
        flagged_phrases = list(verdict_dict.get("flagged_phrases") or [])
        rationale = str(verdict_dict.get("rationale") or "")
        final_confidence = confidence

        iterations.append(
            DetectorIteration(
                iter_n=iter_n,
                confidence=confidence,
                flagged_phrases=flagged_phrases,
                refinements=[],
                rationale=rationale,
            )
        )

        if confidence <= target_confidence:
            target_met = True
            break

        if iter_n + 1 >= max_iters:
            # Last iteration. Don't bother refining — caller takes current text.
            break

        if not flagged_phrases:
            # Nothing actionable to refine; ship current text.
            break

        try:
            refine_result = await llm_tracker.tracked_call(
                session=session,
                user_id=user_id,
                provider=provider,
                method="structured",
                prompt_name="refine_to_human",
                application_id=application_id,
                prompt=build_refine_prompt(current_text, flagged_phrases),
                schema=RefinedText,
                system=system,
                cache_system=cache_system,
            )
        except LLMProviderError as exc:
            log.warning("refine_to_human failed at iter %d: %s", iter_n, exc)
            early_exit = "refine_provider_error"
            break

        refine_dict = refine_result.value or {}
        rewritten = str(refine_dict.get("rewritten") or current_text)
        changes = list(refine_dict.get("changes") or [])
        iterations[-1].refinements = changes
        current_text = rewritten
        refined_count += 1

    # Originality.ai spot-check at convergence — only when we actually
    # refined (no point ground-truth-checking unmodified input).
    originality_score: float | None = None
    api_key = getattr(settings, "originality_api_key", None)
    if api_key and refined_count > 0:
        try:
            originality_score = await originality_score_text(
                text=current_text,
                api_key=api_key,
                session=session,
                user_id=user_id,
                application_id=application_id,
            )
        except Exception as exc:  # noqa: BLE001 — third-party API failure best-effort
            log.warning("originality.ai spot-check failed: %s", exc)
            originality_score = None

    return DetectorReport(
        final_text=current_text,
        final_confidence=final_confidence,
        target_met=target_met,
        iterations=iterations,
        originality_score=originality_score,
        early_exit_reason=early_exit,
    )
