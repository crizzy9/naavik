"""Bullet ranking (LLM), per-bullet JD refine, burstiness regen.

Split out of services/document_generator.py in plan 91 Phase 4.3;
behaviour unchanged. Internal calls to patched seams go through `svc()`
(the facade) so test interception keeps working.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlmodel.ext.asyncio.session import AsyncSession

from llm import LLMProviderError
from models import (
    Bullet,
    Job,
    Settings,
)
from models.enums import BulletSelectionOverride
from services.generation.common import svc
from services.generation.snapshot import ProfileSnapshot, _bullet_inventory

log = logging.getLogger(__name__)


def _resolve_override(
    bullet: Bullet,
    application_overrides: dict[int, str] | None,
) -> BulletSelectionOverride | None:
    """Per-app `bullet_overrides` win over `Bullet.selection_override` (plan 86 / 0.4.5.08).

    Architect R2 round 2 — `PUT /api/v1/applications/{id}/bullet-override`
    writes `submission_artifacts["bullet_overrides"][<str(bid)>]` but the
    document generator previously ignored that dict. Resolution order per
    bullet:
      1. Per-app override (`always_include` / `never_include`) wins.
      2. Model column `Bullet.selection_override`.
      3. `None` (LLM picks).
    Unknown override values silently fall through to the model column —
    defense-in-depth in case future enum additions ship before this resolver.
    """
    if application_overrides:
        raw = application_overrides.get(bullet.id)
        if raw == BulletSelectionOverride.ALWAYS_INCLUDE.value:
            return BulletSelectionOverride.ALWAYS_INCLUDE
        if raw == BulletSelectionOverride.NEVER_INCLUDE.value:
            return BulletSelectionOverride.NEVER_INCLUDE
    return bullet.selection_override


def _split_bullets_by_override(
    bullets: list[Bullet],
    application_overrides: dict[int, str] | None = None,
) -> tuple[list[Bullet], list[Bullet], list[Bullet]]:
    always: list[Bullet] = []
    never: list[Bullet] = []
    auto: list[Bullet] = []
    for b in bullets:
        effective = _resolve_override(b, application_overrides)
        if effective == BulletSelectionOverride.ALWAYS_INCLUDE:
            always.append(b)
        elif effective == BulletSelectionOverride.NEVER_INCLUDE:
            never.append(b)
        else:
            auto.append(b)
    return always, never, auto


async def _ai_rank_bullets(
    *,
    session: AsyncSession,
    settings: Settings,
    snap: ProfileSnapshot,
    job: Job,
    user_id: int,
    application_id: int | None,
    system: str | None = None,
    cache_system: bool = False,
    application_overrides: dict[int, str] | None = None,
) -> list[int]:
    """Return the FULL bullet inventory in priority order, honoring overrides.

    `always_include` bullets lead (profile order); the LLM ranks the rest;
    `never_include` bullets are excluded. The page-fit loop packs from the
    head of this list and drops from the tail.

    `application_overrides` (plan 86 / 0.4.5.08) — per-application bullet
    overrides keyed by bullet id, values `"always_include"` / `"never_include"`.
    Win over the model-level `Bullet.selection_override` column.
    """
    inventory = _bullet_inventory(snap)
    if not inventory:
        return []
    always, never, auto = _split_bullets_by_override(inventory, application_overrides)
    del never

    ranked: list[int] = [b.id for b in always]
    if not auto:
        return ranked

    provider = svc().get_provider(settings)
    bullet_payload = [{"id": b.id, "text": b.text} for b in auto]
    job_payload = {
        "role": job.role,
        "description": job.description or job.description_html or "",
        "skills_required": list(job.skills_required or []),
    }
    try:
        result = await svc().llm_tracker.tracked_call(
            session=session,
            user_id=user_id,
            provider=provider,
            method="structured",
            prompt_name="select_bullets",
            application_id=application_id,
            prompt=_render_rank_prompt(bullet_payload, job_payload),
            schema=__import__(
                "llm.prompts.select_bullets", fromlist=["BulletSelection"]
            ).BulletSelection,
            system=system,
            cache_system=cache_system,
        )
        chosen = list(result.value.get("selected_ids", [])) if result else []
    except LLMProviderError as exc:
        log.warning("select_bullets LLM failed; falling back to profile order: %s", exc)
        chosen = [b.id for b in auto]
    # Defend against the model returning ids outside the auto pool, and
    # re-append anything it omitted so no bullet silently vanishes from the
    # candidate pool (it can still be dropped by the page-fit loop).
    auto_ids = {b.id for b in auto}
    seen: set[int] = set()
    cleaned: list[int] = []
    for cid in chosen:
        if cid in auto_ids and cid not in seen:
            seen.add(cid)
            cleaned.append(cid)
    for b in auto:
        if b.id not in seen:
            cleaned.append(b.id)
    ranked.extend(cleaned)
    return ranked


def _render_rank_prompt(bullets: list[dict], job: dict) -> str:
    from llm.prompts.select_bullets import PROMPT as RANK_PROMPT

    lines = "\n".join(f"{b['id']} → {b['text']}" for b in bullets)
    return RANK_PROMPT.format(
        bullets=lines,
        role=job.get("role", ""),
        description=(job.get("description") or "")[:1500],
        skills=", ".join(job.get("skills_required", [])),
    )


async def _tailor_summary(
    *,
    session: AsyncSession,
    settings: Settings,
    snap: ProfileSnapshot,
    job: Job,
    user_id: int,
    application_id: int | None,
    ranked_bullet_ids: list[int],
    system: str | None = None,
    cache_system: bool = False,
) -> str | None:
    """JD-tailored 2–3 line summary pitch. Falls back to the profile summary."""
    from llm.prompts.tailor_summary import TailoredSummary, render_prompt

    p = snap.profile
    fallback = p.summary_short or p.summary_full
    by_id = {b.id: b for b in _bullet_inventory(snap)}
    top_bullets = [by_id[bid].text for bid in ranked_bullet_ids[:8] if bid in by_id]
    profile_text = (
        f"Headline: {p.headline or '(none)'}\n"
        f"Current summary: {fallback or '(none)'}\n"
        f"Skills: {', '.join(item for s in snap.skills for item in (s.items or [])[:6])[:400]}"
    )
    job_text = (
        f"{job.company} — {job.role}\n{(job.description or job.description_html or '')[:1500]}"
    )
    try:
        provider = svc().get_provider(settings)
        result = await svc().llm_tracker.tracked_call(
            session=session,
            user_id=user_id,
            provider=provider,
            method="structured",
            prompt_name="tailor_summary",
            application_id=application_id,
            prompt=render_prompt(
                name=p.full_name, profile_text=profile_text, bullets=top_bullets, job_text=job_text
            ),
            schema=TailoredSummary,
            system=system,
            cache_system=cache_system,
        )
        summary = str(result.value.get("summary") or "").strip()
        return summary or fallback
    except LLMProviderError as exc:
        log.warning("tailor_summary failed; using profile summary: %s", exc)
        return fallback


# One printed line in `onepage.typ` (10pt New Computer Modern, 0.3in
# margins, ∘ + 0.15in list indent, justified) holds ~125+ characters — the
# cv.tex reference's longest bullet (127 chars) fits on one line. The
# refine TARGET stays 112 with capacity 118: both are safely under the true
# wrap point, and the eval harness checks capacity, not the target — a
# 115-char line renders fine and shouldn't be flagged.
RESUME_BULLET_CHAR_BUDGET = 112
RESUME_BULLET_LINE_CAPACITY = 118

# JD excerpt cap for the per-bullet refine prompt — full JDs blow up the
# token bill × ~20 bullets per generation.
_REFINE_JD_CHARS = 2400


async def _refine_one_bullet(
    *,
    session: AsyncSession,
    settings: Settings,
    user_id: int,
    application_id: int | None,
    bullet: Bullet,
    job_text: str,
    target_chars: int = RESUME_BULLET_CHAR_BUDGET,
    system: str | None = None,
    cache_system: bool = False,
) -> str:
    """Rewrite one bullet against the JD (mirror truthful terminology) AND
    enforce the one-line character budget.

    Every selected bullet goes through one refine call; a result over
    budget gets ONE stricter retry, then falls back to the shorter of the
    two candidates (the page-fit loop + eval scorecard catch stragglers).
    LLM failure degrades to plain truncation of the original.
    """
    from llm.prompts.refine_bullet import PROMPT as REFINE_PROMPT
    from llm.prompts.refine_bullet import RefinedBullet

    provider = svc().get_provider(settings)

    async def _call(target: int, text: str) -> str | None:
        try:
            result = await svc().llm_tracker.tracked_call(
                session=session,
                user_id=user_id,
                provider=provider,
                method="structured",
                prompt_name="refine_bullet",
                application_id=application_id,
                prompt=REFINE_PROMPT.format(
                    job_text=job_text[:_REFINE_JD_CHARS], text=text, target_chars=target
                ),
                schema=RefinedBullet,
                system=system,
                cache_system=cache_system,
            )
            refined = str(result.value.get("refined") or "").strip()
            return refined or None
        except LLMProviderError as exc:
            log.warning("refine_bullet failed: %s", exc)
            return None

    first = await _call(target_chars, bullet.text)
    if first is None:
        # No provider / hard failure — degrade honestly to a trim.
        if len(bullet.text) <= target_chars:
            return bullet.text
        return bullet.text[: target_chars - 1] + "…"
    if len(first) <= target_chars:
        return first
    second = await _call(int(target_chars * 0.9), first)
    candidates = [c for c in (first, second) if c]
    fitting = [c for c in candidates if len(c) <= target_chars]
    if fitting:
        return fitting[0]
    return min(candidates, key=len)


def _format_date(d: datetime | None) -> str | None:
    if d is None:
        return None
    return d.strftime("%b %Y")


async def regen_bullet_for_variance(
    *,
    session: AsyncSession,
    settings: Settings,
    user_id: int,
    application_id: int | None,
    original_text: str,
    target: str,
    target_words: int | None,
    system: str | None = None,
    cache_system: bool = False,
) -> str:
    """Re-prompt one bullet with explicit sentence-length variance instruction.

    Plan 75 / 0.3.3.05 — burstiness regen path. Caller (`bundle_generator`)
    invokes when std-dev of trimmed bullet word counts falls below the
    threshold; this helper asks the LLM to rewrite the worst-offender
    bullet with a different sentence structure / word-count target so the
    overall batch reads as more human-varied.

    `target` is "short" or "long" (from BurstinessReport); `target_words`
    is the suggested approximate word count.

    Returns the regenerated bullet on success; the `original_text`
    unchanged on LLM failure (caller decides whether to substitute).
    """
    target_phrase = (
        f"approximately {target_words} words" if target_words else "noticeably different length"
    )
    direction = (
        "Use a shorter, punchier sentence with a different opening verb."
        if target == "short"
        else "Expand with one additional concrete result or qualifier; keep all numbers."
    )
    prompt = (
        "Rewrite this resume bullet with a DIFFERENT sentence structure than the "
        f"original. Target {target_phrase}. {direction} Preserve every number, "
        "every concrete result, and the original verb's intent.\n\n"
        f"Original:\n{original_text}\n\n"
        "Return TrimmedBullet with trimmed + dropped_phrases."
    )
    try:
        provider = svc().get_provider(settings)
        result = await svc().llm_tracker.tracked_call(
            session=session,
            user_id=user_id,
            provider=provider,
            method="structured",
            prompt_name="regen_bullet_variance",
            application_id=application_id,
            prompt=prompt,
            schema=__import__("llm.prompts.trim_bullet", fromlist=["TrimmedBullet"]).TrimmedBullet,
            system=system,
            cache_system=cache_system,
        )
        return str(result.value.get("trimmed") or original_text)
    except LLMProviderError as exc:
        # `get_provider` raises `LLMProviderError(kind="provider_error")` when
        # no provider is configured — same failure surface as a runtime LLM
        # call. Tests that don't pre-configure a provider (the bulk of the
        # bundle_generator suite) tolerate the regen no-op via this path.
        #
        # Plan 85 / 0.3.3.24 — bumped to ERROR (was WARNING) so debuggers
        # reading prod logs notice that a regen attempt was made and failed.
        # The caller (bundle_generator) marks `burstiness_regen_failed=True`
        # in the audit trail when the helper returns the same `original_text`
        # via the structured return path; this log line is the in-process
        # complement that survives without the caller's trace context.
        log.error("regen_bullet_for_variance failed; preserving original: %s", exc)
        return original_text
