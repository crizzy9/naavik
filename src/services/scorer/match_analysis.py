"""Lazy review-panel match analysis — per-requirement coverage + keyword strengths/gaps.

Runs the first time a job's review workspace opens (NOT at bulk-scoring
time — reviewed jobs are a small fraction of scored jobs) and persists
into `Job.match_breakdown`:

    "strengths": [...keywords...],          # overwrites the judge's prose
    "gaps": [...keywords...],
    "requirements_coverage": {
        "criteria_hash": "<sha256[:16] of the criteria slice>",
        "covered": [bool, ...],             # aligned to criteria[:LIMIT]
        "refreshed_at": "<iso ts>",
    }

Re-runs only when the criteria hash changes (JD re-extracted). LLM
failures stamp `analysis_failed_at` so the workspace's 3s generation poll
doesn't hammer a broken provider; no provider configured skips silently
(the token heuristic in discover_review_ctx keeps working).
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime, timedelta

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from llm import LLMProviderError, get_provider
from llm.prompts.match_analysis import MAX_KEYWORDS, PROMPT, MatchAnalysis
from models import Experience, Job, Profile, Skill
from services import llm_tracker

log = logging.getLogger(__name__)

# Matches the slice build_review_ctx feeds the WHAT THEY WANT column.
CRITERIA_LIMIT = 8
_FAIL_COOLDOWN = timedelta(minutes=10)
_MAX_BULLETS = 15


def criteria_hash(criteria: list[str]) -> str:
    return hashlib.sha256("\n".join(criteria).encode("utf-8")).hexdigest()[:16]


def _parse_ts(raw: object) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


async def ensure_match_analysis(session: AsyncSession, *, job: Job, user_id: int) -> bool:
    """Compute + persist the review-panel analysis for `job` if absent/stale.

    Returns True when a fresh analysis was persisted this call. Commits on
    success (lazy cache write from GET routes; expire_on_commit=False).
    Never raises — every failure degrades to the existing breakdown.
    """
    breakdown = dict(job.match_breakdown or {})
    if not breakdown or "score" not in breakdown:
        return False  # unscored job — the panel renders nothing to fix

    criteria = [c for c in (job.criteria or []) if c][:CRITERIA_LIMIT]
    chash = criteria_hash(criteria)
    existing = breakdown.get("requirements_coverage") or {}
    if isinstance(existing, dict) and existing.get("criteria_hash") == chash:
        return False

    failed_at = _parse_ts(breakdown.get("analysis_failed_at"))
    if failed_at is not None and datetime.now(UTC) - failed_at < _FAIL_COOLDOWN:
        return False

    from services import settings as settings_service

    try:
        user_settings = await settings_service.get_or_create(session, user_id=user_id)
        provider = get_provider(user_settings)
    except LLMProviderError:
        return False  # no provider — heuristic marks keep working

    profile = (
        await session.exec(
            select(Profile).where(Profile.user_id == user_id, Profile.deleted_at.is_(None))
        )
    ).one_or_none()
    if profile is None:
        return False

    skills = (
        await session.exec(
            select(Skill).where(Skill.profile_id == profile.id).order_by(Skill.order_index)
        )
    ).all()
    experiences = (
        await session.exec(
            select(Experience)
            .where(Experience.profile_id == profile.id, Experience.deleted_at.is_(None))
            .order_by(Experience.order_index)
        )
    ).all()
    from models import Bullet

    bullets: list[str] = []
    for exp in experiences:
        rows = (
            await session.exec(
                select(Bullet)
                .where(Bullet.experience_id == exp.id, Bullet.deleted_at.is_(None))
                .order_by(Bullet.order_index)
            )
        ).all()
        bullets.extend((b.text or "")[:200] for b in rows)
        if len(bullets) >= _MAX_BULLETS:
            break

    from services.profile import total_years_experience

    years = total_years_experience(list(experiences))
    prompt = PROMPT.format(
        company=job.company or "",
        role=job.role or "",
        description=(job.description or job.description_html or "")[:2500],
        requirements="\n".join(f"{i} → {c}" for i, c in enumerate(criteria)) or "(none)",
        skills_inventory="\n".join(f"- {s.category}: {', '.join(s.items or [])}" for s in skills)
        or "(none listed)",
        titles=", ".join(e.title for e in experiences if e.title) or "(none)",
        years_experience=f"~{years:.1f} years" if years is not None else "unknown",
        summary=(profile.summary_full or profile.summary_short or "(none)")[:800],
        bullets="\n".join(f"- {b}" for b in bullets[:_MAX_BULLETS]) or "(none)",
        max_keywords=MAX_KEYWORDS,
    )

    try:
        result = await llm_tracker.tracked_call(
            session=session,
            user_id=user_id,
            provider=provider,
            method="structured",
            prompt_name="match_analysis",
            prompt=prompt,
            schema=MatchAnalysis,
        )
        analysis = MatchAnalysis.model_validate(getattr(result, "value", result))
    except (LLMProviderError, ValueError) as exc:
        log.warning("match_analysis failed for job %s: %s", job.id, exc)
        breakdown["analysis_failed_at"] = datetime.now(UTC).isoformat()
        job.match_breakdown = breakdown
        session.add(job)
        await session.commit()
        return False

    covered = [False] * len(criteria)
    for entry in analysis.requirements:
        if 0 <= entry.index < len(covered):
            covered[entry.index] = entry.covered

    breakdown["strengths"] = analysis.strengths
    breakdown["gaps"] = analysis.gaps
    breakdown["requirements_coverage"] = {
        "criteria_hash": chash,
        "covered": covered,
        "refreshed_at": datetime.now(UTC).isoformat(),
    }
    breakdown.pop("analysis_failed_at", None)
    job.match_breakdown = breakdown
    session.add(job)
    await session.commit()
    return True


__all__ = ["CRITERIA_LIMIT", "criteria_hash", "ensure_match_analysis"]
