"""Layered scoring orchestrator (plan 65 § D.6 + § T1-T11).

End-to-end driver for the 4-layer scorer:

    1a. Visa filter (deterministic — zeroes out non-sponsorable jobs)
    1b. Tag overlap (weighted) — gate at `_TAG_FLOOR = 0.10`
    2.  Semantic cosine (pgvector) — composite = 0.4·tag + 0.6·semantic
    3.  LLM-as-judge — fires only when composite ≥ `_LLM_GATE = 0.50` and
        cost cap allows (per-job probe).

Writes `Job.score`, `Job.score_explanation`, `Job.match_breakdown`
(T7 17-key shape with `schema_version=1`), bumps `Job.updated_at`.
Does NOT emit AppEvent (T8). Cost-cap fallback + LLM-failed fallback
both surface `judge_skipped=true` + a reason so Settings UI can show
the cap banner (UI ships in 0.3.2.04).

Forward-compat seam: `source_trust_weight` is a kwarg threaded through
to multipy the final score; v1 hardcodes 1.0 from every callsite. The
seam unblocks `0.8.0.42` per-source weighting without refactoring this
module.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text as sql_text
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from llm.prompts.score_job import JobScore
from models import (
    Bullet,
    Experience,
    Job,
    Profile,
    ProfileEmbedding,
    Settings,
)

from . import (
    _BATCH_SIZE,
    _ESTIMATED_JUDGE_COST_USD,  # noqa: F401 — referenced in tests, surface kept
    _K_CANDIDATE_BULLETS,
    _LLM_GATE,
    _SEMANTIC_WEIGHT,
    _TAG_FLOOR,
    _TAG_WEIGHT,
)
from .llm_judge import _llm_judge_score, cost_cap_exhausted
from .semantic_layer import _semantic_score
from .tag_layer import _tag_overlap_score, aggregated_profile_tags
from .visa import apply_visa_filter, needs_visa_zero_out
from .weights import resolve_weights

log = logging.getLogger(__name__)

_SCHEMA_VERSION = 1


def _build_breakdown(
    *,
    score: float,
    matched_tags: list[str],
    per_dimension: dict[str, float],
    strengths: list[str],
    gaps: list[str],
    suggested_bullets: list[int],
    visa_concern: bool,
    visa_note: str | None,
    layers_run: list[str],
    judge_skipped: bool,
    judge_skipped_reason: str | None,
    layer_4_provider: str | None,
    layer_4_model: str | None,
    tag_score: float,
    semantic_score: float | None,
    composite_pre_llm: float,
) -> dict[str, Any]:
    """Materialize the T7 canonical match_breakdown shape."""
    return {
        "score": round(score, 6),
        "per_dimension": per_dimension or {},
        "matched_tags": matched_tags or [],
        "strengths": strengths or [],
        "gaps": gaps or [],
        "suggested_bullets": suggested_bullets or [],
        "visa_concern": bool(visa_concern),
        "visa_note": visa_note,
        "layers_run": layers_run,
        "judge_skipped": bool(judge_skipped),
        "judge_skipped_reason": judge_skipped_reason,
        "layer_4_provider": layer_4_provider,
        "layer_4_model": layer_4_model,
        "scored_at": datetime.now(UTC).isoformat(),
        "tag_score": round(tag_score, 6),
        "semantic_score": (round(semantic_score, 6) if semantic_score is not None else None),
        "composite_pre_llm": round(composite_pre_llm, 6),
        "schema_version": _SCHEMA_VERSION,
    }


async def _persist_score(
    session: AsyncSession,
    *,
    job: Job,
    score_value: float,
    explanation: str,
    breakdown: dict[str, Any],
) -> None:
    """Write Job.score + Job.score_explanation + Job.match_breakdown atomically.

    Bumps `Job.updated_at`. Does NOT emit AppEvent (per T8).
    """
    job.score = float(max(0.0, min(1.0, score_value)))
    job.score_explanation = explanation
    job.match_breakdown = breakdown
    job.updated_at = datetime.now(UTC)
    session.add(job)
    await session.flush()


async def _select_candidate_bullets(
    session: AsyncSession,
    *,
    profile: Profile,
    job: Job,
    k: int = _K_CANDIDATE_BULLETS,
) -> list[Bullet]:
    """Top-K bullets ordered by tag-overlap-count with `job.tags` DESC.

    Pulls the profile's bullets, sorts in Python by overlap count (cheap
    at <=200 bullets per profile), returns the top K. LLM then selects
    up to MAX_SUGGESTED_BULLETS (=8) from the K we pass.
    """
    if profile is None or profile.id is None:
        return []
    stmt = (
        select(Bullet)
        .join(Experience, Bullet.experience_id == Experience.id)
        .where(
            Experience.profile_id == profile.id,
            Bullet.deleted_at.is_(None),
            Experience.deleted_at.is_(None),
        )
    )
    bullets = list((await session.exec(stmt)).all())
    job_tags = set(job.tags or [])

    def _overlap(b: Bullet) -> int:
        return len(set(b.tags or []) & job_tags)

    bullets.sort(key=_overlap, reverse=True)
    return bullets[:k]


async def _filter_valid_bullet_ids(
    session: AsyncSession,
    *,
    user_id: int,
    profile_id: int | None,
    ids: list[int],
) -> list[int]:
    """Keep only Bullet.ids that exist + belong to this user's profile.

    Defends against LLM hallucination (IDOR-flavored). The user_id check
    flows through `Bullet → Experience.profile_id → Profile.user_id` chain.
    """
    if not ids or profile_id is None:
        return []
    stmt = (
        select(Bullet.id)
        .join(Experience, Bullet.experience_id == Experience.id)
        .where(
            Experience.profile_id == profile_id,
            Bullet.id.in_(ids),
            Bullet.deleted_at.is_(None),
            Experience.deleted_at.is_(None),
        )
    )
    rows = (await session.exec(stmt)).all()
    valid = {int(r) for r in rows}
    # Preserve LLM's order, drop hallucinated IDs.
    out = [i for i in ids if i in valid]
    return out


async def score_job_layered(
    session: AsyncSession,
    *,
    user_id: int,
    job: Job,
    profile: Profile,
    settings: Settings,
    source_trust_weight: float = 1.0,
) -> JobScore:
    """End-to-end layered scoring for one job. Persists side effects.

    Returns the final `JobScore` (also persisted on the Job row).
    `source_trust_weight` is the forward-compat seam (T9) — v1 callers
    pass the default 1.0; `0.8.0.42` will pass per-source values.
    """
    # ── Layer 1a — deterministic visa filter ──────────────────────────
    if needs_visa_zero_out(profile, job):
        visa_note = str(job.visa_restrictions) if job.visa_restrictions is not None else None
        score = JobScore(
            score=0.0,
            explanation=(
                "Visa filter: job requires US citizenship / green card; "
                "candidate needs sponsorship now."
            ),
            visa_concern=True,
            visa_note=visa_note,
        )
        breakdown = _build_breakdown(
            score=0.0,
            matched_tags=list(score.matched_tags),
            per_dimension={},
            strengths=[],
            gaps=list(score.gaps),
            suggested_bullets=[],
            visa_concern=True,
            visa_note=visa_note,
            layers_run=["visa"],
            judge_skipped=True,
            judge_skipped_reason="visa_zeroed",
            layer_4_provider=None,
            layer_4_model=None,
            tag_score=0.0,
            semantic_score=None,
            composite_pre_llm=0.0,
        )
        await _persist_score(
            session,
            job=job,
            score_value=0.0,
            explanation=score.explanation,
            breakdown=breakdown,
        )
        return score

    # ── Layer 1b — tag overlap ────────────────────────────────────────
    profile_tags = await aggregated_profile_tags(session, profile=profile)
    weights = resolve_weights(settings)
    tag_score = _tag_overlap_score(job.tags or [], profile_tags, weights)

    if tag_score < _TAG_FLOOR:
        composite = tag_score * source_trust_weight
        explanation = f"Below tag floor — only {tag_score:.2f} of job's tags covered by profile."
        score = JobScore(score=max(0.0, min(1.0, composite)), explanation=explanation)
        breakdown = _build_breakdown(
            score=composite,
            matched_tags=list(set(job.tags or []) & profile_tags),
            per_dimension={},
            strengths=[],
            gaps=[],
            suggested_bullets=[],
            visa_concern=False,
            visa_note=None,
            layers_run=["tag"],
            judge_skipped=True,
            judge_skipped_reason="below_tag_floor",
            layer_4_provider=None,
            layer_4_model=None,
            tag_score=tag_score,
            semantic_score=None,
            composite_pre_llm=composite,
        )
        await _persist_score(
            session,
            job=job,
            score_value=composite,
            explanation=explanation,
            breakdown=breakdown,
        )
        return score

    # ── Layer 2 — semantic cosine ─────────────────────────────────────
    profile_emb = (
        await session.exec(select(ProfileEmbedding).where(ProfileEmbedding.user_id == user_id))
    ).one_or_none()
    semantic = await _semantic_score(session, job=job, profile_embedding=profile_emb)

    if semantic is None:
        composite = tag_score
        layers_run = ["tag"]
    else:
        composite = _TAG_WEIGHT * tag_score + _SEMANTIC_WEIGHT * semantic
        layers_run = ["tag", "semantic"]

    composite *= source_trust_weight
    composite = max(0.0, min(1.0, composite))

    if composite < _LLM_GATE:
        explanation = (
            f"Tag + semantic composite ({composite:.2f}) below LLM threshold; judge skipped."
        )
        score = JobScore(score=composite, explanation=explanation)
        breakdown = _build_breakdown(
            score=composite,
            matched_tags=list(set(job.tags or []) & profile_tags),
            per_dimension={},
            strengths=[],
            gaps=[],
            suggested_bullets=[],
            visa_concern=False,
            visa_note=None,
            layers_run=layers_run,
            judge_skipped=True,
            judge_skipped_reason="below_llm_gate",
            layer_4_provider=None,
            layer_4_model=None,
            tag_score=tag_score,
            semantic_score=semantic,
            composite_pre_llm=composite,
        )
        await _persist_score(
            session,
            job=job,
            score_value=composite,
            explanation=explanation,
            breakdown=breakdown,
        )
        return score

    # ── Layer 3 — LLM-as-judge (cost-cap probe per T1) ────────────────
    if await cost_cap_exhausted(session, user_id=user_id, settings=settings):
        explanation = (
            f"Tag + semantic composite ({composite:.2f}); "
            "LLM judge paused — daily cost cap reached."
        )
        score = JobScore(score=composite, explanation=explanation)
        breakdown = _build_breakdown(
            score=composite,
            matched_tags=list(set(job.tags or []) & profile_tags),
            per_dimension={},
            strengths=[],
            gaps=[],
            suggested_bullets=[],
            visa_concern=False,
            visa_note=None,
            layers_run=layers_run,
            judge_skipped=True,
            judge_skipped_reason="cost_cap_exhausted",
            layer_4_provider=None,
            layer_4_model=None,
            tag_score=tag_score,
            semantic_score=semantic,
            composite_pre_llm=composite,
        )
        await _persist_score(
            session,
            job=job,
            score_value=composite,
            explanation=explanation,
            breakdown=breakdown,
        )
        return score

    candidate_bullets = await _select_candidate_bullets(session, profile=profile, job=job)
    judge_result, skip_reason = await _llm_judge_score(
        session,
        user_id=user_id,
        job=job,
        profile=profile,
        candidate_bullets=candidate_bullets,
        tag_score=tag_score,
        semantic_score=semantic,
        settings=settings,
    )
    if judge_result is None:
        explanation = (
            f"Tag + semantic composite ({composite:.2f}); LLM judge unavailable ({skip_reason})."
        )
        score = JobScore(score=composite, explanation=explanation)
        breakdown = _build_breakdown(
            score=composite,
            matched_tags=list(set(job.tags or []) & profile_tags),
            per_dimension={},
            strengths=[],
            gaps=[],
            suggested_bullets=[],
            visa_concern=False,
            visa_note=None,
            layers_run=layers_run,
            judge_skipped=True,
            judge_skipped_reason=skip_reason or "llm_failed",
            layer_4_provider=None,
            layer_4_model=None,
            tag_score=tag_score,
            semantic_score=semantic,
            composite_pre_llm=composite,
        )
        await _persist_score(
            session,
            job=job,
            score_value=composite,
            explanation=explanation,
            breakdown=breakdown,
        )
        return score

    # ── Filter hallucinated bullet IDs (T9) ───────────────────────────
    if judge_result.suggested_bullets:
        valid_ids = await _filter_valid_bullet_ids(
            session,
            user_id=user_id,
            profile_id=profile.id,
            ids=list(judge_result.suggested_bullets),
        )
        if len(valid_ids) < len(judge_result.suggested_bullets) / 2:
            log.warning(
                "scorer judge hallucinated %d/%d bullet IDs for job %s",
                len(judge_result.suggested_bullets) - len(valid_ids),
                len(judge_result.suggested_bullets),
                job.id,
            )
        judge_result = judge_result.model_copy(update={"suggested_bullets": valid_ids})

    # Belt-and-suspenders visa filter even after LLM (LLM may miss).
    final_score = apply_visa_filter(judge_result, profile, job)

    # source_trust_weight already applied to composite; multiply LLM score too.
    weighted_value = max(0.0, min(1.0, final_score.score * source_trust_weight))
    final_score = final_score.model_copy(update={"score": weighted_value})

    breakdown = _build_breakdown(
        score=final_score.score,
        matched_tags=list(final_score.matched_tags),
        per_dimension=dict(final_score.per_dimension),
        strengths=list(final_score.strengths),
        gaps=list(final_score.gaps),
        suggested_bullets=list(final_score.suggested_bullets),
        visa_concern=final_score.visa_concern,
        visa_note=final_score.visa_note,
        layers_run=layers_run + ["llm_judge"],
        judge_skipped=False,
        judge_skipped_reason=None,
        layer_4_provider=(
            settings.llm_provider.value
            if hasattr(settings.llm_provider, "value")
            else str(settings.llm_provider)
        ),
        layer_4_model=settings.llm_model,
        tag_score=tag_score,
        semantic_score=semantic,
        composite_pre_llm=composite,
    )
    await _persist_score(
        session,
        job=job,
        score_value=final_score.score,
        explanation=final_score.explanation,
        breakdown=breakdown,
    )
    return final_score


# ── Cron entries (plan 65 § T10) ──────────────────────────────────────


async def score_unscored_jobs(
    session: AsyncSession,
    *,
    batch_size: int = _BATCH_SIZE,
) -> int:
    """`jobs.score_pending` cron entry (T10).

    For each user with `Settings.semantic_match_enabled = True`, score
    their `Job.score == 0.0 AND deleted_at IS NULL` rows up to batch_size
    per invocation. Returns total jobs scored (sum across users).

    Returns 0 if no work — cron is idempotent.
    """
    users_stmt = select(Settings).where(Settings.semantic_match_enabled.is_(True))
    users = (await session.exec(users_stmt)).all()

    total = 0
    for settings_row in users:
        profile = (
            await session.exec(select(Profile).where(Profile.user_id == settings_row.user_id))
        ).one_or_none()
        if profile is None:
            continue

        jobs_stmt = (
            select(Job)
            .where(
                Job.user_id == settings_row.user_id,
                Job.score == 0.0,
                Job.deleted_at.is_(None),
            )
            .limit(batch_size)
        )
        jobs = (await session.exec(jobs_stmt)).all()
        for job in jobs:
            try:
                await score_job_layered(
                    session,
                    user_id=settings_row.user_id,
                    job=job,
                    profile=profile,
                    settings=settings_row,
                )
                total += 1
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "score_unscored_jobs error scoring job %s for user %s: %s",
                    job.id,
                    settings_row.user_id,
                    exc,
                )
    return total


async def rescore_stale_jobs(
    session: AsyncSession,
    *,
    batch_size: int = _BATCH_SIZE,
) -> int:
    """`score.recompute_stale` cron — re-score jobs whose Profile changed
    since last scoring (T10).

    Uses `Job.match_breakdown ->> 'scored_at' < Profile.updated_at` to
    detect staleness. Postgres-only via the JSONB extractor; on sqlite
    the query degrades to a no-op (returns 0).
    """
    bind = session.bind if hasattr(session, "bind") else None
    is_postgres = (
        bool(bind) and getattr(bind, "dialect", None) and bind.dialect.name == "postgresql"
    )
    if not is_postgres:
        # sqlite has no JSONB extractor; skip on test fixtures + log.
        log.debug("rescore_stale_jobs skipped on non-postgres dialect")
        return 0

    users_stmt = select(Settings).where(Settings.semantic_match_enabled.is_(True))
    users = (await session.exec(users_stmt)).all()

    total = 0
    for settings_row in users:
        profile = (
            await session.exec(select(Profile).where(Profile.user_id == settings_row.user_id))
        ).one_or_none()
        if profile is None:
            continue

        # Postgres JSONB extractor — pulls scored_at and compares to profile.updated_at.
        stmt = sql_text(
            """
            SELECT j.id FROM job j
            WHERE j.user_id = :uid
              AND j.deleted_at IS NULL
              AND (j.match_breakdown->>'scored_at')::timestamptz IS NOT NULL
              AND (j.match_breakdown->>'scored_at')::timestamptz < :prof_updated
            ORDER BY j.id ASC
            LIMIT :lim
            """
        )
        rows = (
            await session.exec(
                stmt.bindparams(
                    uid=settings_row.user_id,
                    prof_updated=profile.updated_at,
                    lim=batch_size,
                )
            )
        ).all()
        job_ids = [int(r[0] if isinstance(r, tuple) else r) for r in rows]
        for jid in job_ids:
            job = (await session.exec(select(Job).where(Job.id == jid))).one_or_none()
            if job is None:
                continue
            try:
                await score_job_layered(
                    session,
                    user_id=settings_row.user_id,
                    job=job,
                    profile=profile,
                    settings=settings_row,
                )
                total += 1
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "rescore_stale_jobs error scoring job %s for user %s: %s",
                    jid,
                    settings_row.user_id,
                    exc,
                )
    return total


__all__ = [
    "_build_breakdown",
    "_filter_valid_bullet_ids",
    "_persist_score",
    "_select_candidate_bullets",
    "rescore_stale_jobs",
    "score_job_layered",
    "score_unscored_jobs",
]
