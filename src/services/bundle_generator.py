"""Bundle generator — plan 66 (0.3.1) § B.6.

Orchestrates the full FREE-tier generation pipeline for one
`Application`. Produces:

- Resume PDF (template auto-selected by `Application.board`)
- Cover letter PDF (adaptive format — Standard or Pain-Letter)
- Screener answers (auto-fill + LLM-draft + reuse-cache hit)
- `Application.generation_trace` JSONB audit trail (17 keys, T14)

Cost-cap probe between stages (T13) — graceful skip + `degraded_mode`
marker when today's spend crosses `Settings.daily_llm_cost_cap_usd`.

Ethics pre-flight (B.6) drops bullets without profile provenance. When
>2 bullets get dropped, the bundle surfaces a red-flag to the user.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import (
    Application,
    ApplicationScreenerAnswer,
    Experience,
    GeneratedDocument,
    Job,
    Profile,
    Settings,
)
from services import document_generator as dg
from services.ats_parser_fidelity import (
    ParseScoreReport,
    validate_parse_fidelity,
)
from services.ethics_preflight import EthicsReport, preflight_check
from services.hiring_manager_extractor import HiringManagerHit, extract_hiring_manager
from services.keyword_coverage import CoverageReport, compute_coverage
from services.recruiter_optimization import (
    HEADLINE_SCORE_GATE,
    tailor_headline_for_application,
)
from services.voice_grounding import VoiceCorpus, assemble_corpus

log = logging.getLogger(__name__)

GENERATION_TRACE_SCHEMA_VERSION = 1


@dataclass(slots=True)
class BundleResult:
    """End-to-end bundle generation result for one application.

    `degraded=True` when cost-cap fired mid-flight; check
    `degraded_reason` for the specific cause. `ethics` carries the
    pre-flight verdict (surface to user when `ethics.surface_to_user`).
    """

    resume: GeneratedDocument | None = None
    cover_letter: GeneratedDocument | None = None
    screeners: list[ApplicationScreenerAnswer] = field(default_factory=list)
    generation_trace: dict[str, Any] = field(default_factory=dict)
    degraded: bool = False
    degraded_reason: str | None = None
    parse_fidelity: ParseScoreReport | None = None
    keyword_coverage: CoverageReport | None = None
    hiring_manager: HiringManagerHit | None = None
    ethics: EthicsReport | None = None
    skipped_reason: str | None = None  # set when whole bundle bailed before stage 1


async def _initial_trace(*, settings: Settings, corpus: VoiceCorpus | None) -> dict[str, Any]:
    """Boilerplate fields applied to every trace at start of run."""
    return {
        "schema_version": GENERATION_TRACE_SCHEMA_VERSION,
        "tier": "free",
        "stages_run": [],
        "stages_skipped": [],
        "stage_costs_usd": {},
        "total_cost_usd": 0.0,
        "total_latency_ms": 0,
        "llm_calls": 0,
        "bullet_selections": [],
        "jd_keywords_extracted": [],
        "cover_letter_format": "standard",
        "hiring_manager": None,
        "voice_fingerprint_hash": corpus.voice_fingerprint_hash if corpus else None,
        "constitution_version": "v1",
        "parse_fidelity_score": None,
        "parse_fidelity_tier": None,
        "parse_fidelity_fields_missing": [],
        "keyword_coverage_score": None,
        "keyword_coverage_missing": [],
        "ai_tell_violations": [],
        "burstiness_std": None,
        "ethics_pre_flight": {"passed": True, "dropped_bullets": [], "flags": []},
        "degraded_mode": False,
        "cost_cap_at_exhaustion": None,
        "headline_used": None,
        "generated_at": datetime.now(UTC).isoformat(),
    }


async def _load_profile_experiences(
    session: AsyncSession, user_id: int
) -> tuple[Profile | None, list[Experience]]:
    profile = (
        await session.exec(
            select(Profile).where(Profile.user_id == user_id, Profile.deleted_at.is_(None))
        )
    ).one_or_none()
    if profile is None:
        return None, []
    experiences = (
        await session.exec(
            select(Experience)
            .where(Experience.profile_id == profile.id, Experience.deleted_at.is_(None))
            .order_by(Experience.order_index)
        )
    ).all()
    return profile, list(experiences)


async def _persist_trace(
    session: AsyncSession, application: Application, trace: dict[str, Any]
) -> None:
    """Write `trace` to `application.generation_trace`. OVERWRITES (no append)."""
    application.generation_trace = trace
    application.updated_at = datetime.now(UTC)
    session.add(application)
    await session.flush()


def _extract_must_haves(job: Job, job_score_breakdown: dict | None = None) -> list[str]:
    """JD must-haves = matched_tags ∪ Job.skills_required[:5]."""
    must_haves: list[str] = []
    if job_score_breakdown:
        matched_tags = job_score_breakdown.get("matched_tags") or []
        must_haves.extend(str(t) for t in matched_tags)
    must_haves.extend(str(s) for s in (job.skills_required or [])[:5])
    # Dedupe in-order
    seen: set[str] = set()
    out: list[str] = []
    for kw in must_haves:
        norm = kw.lower().strip()
        if norm and norm not in seen:
            seen.add(norm)
            out.append(kw)
    return out


def _resume_text_for_coverage(resume: GeneratedDocument | None) -> str:
    """Render the resume's selected text for coverage scanning.

    We use the `bullet_selection.trimmed_lines` payload (already on the
    `GeneratedDocument`) rather than re-extracting from the PDF — same
    signal, faster, no pdfplumber call.
    """
    if resume is None or not resume.bullet_selection:
        return ""
    trimmed = resume.bullet_selection.get("trimmed_lines") or {}
    if not isinstance(trimmed, dict):
        return ""
    return "\n".join(str(v) for v in trimmed.values() if v)


async def generate_bundle(
    session: AsyncSession,
    application: Application,
    *,
    settings: Settings,
    job: Job | None = None,
    hiring_manager_override: str | None = None,
) -> BundleResult:
    """Generate the full bundle for `application`. Honors cost-cap mid-flight.

    Stages (T13 — cost-cap probe between each):

    1. corpus assembly (voice grounding)
    2. hiring manager extraction
    3. resume generation (existing `generate_resume` — includes select +
       trim + page-count retry; we add ethics pre-flight on its bullet
       output AFTER the fact, since the existing pipeline is a single
       atomic call)
    4. tailored headline (gated on `Job.score ≥ HEADLINE_SCORE_GATE`)
    5. cover letter generation (existing `generate_cover_letter` —
       0.3.1 uses the SOTA prompt under the hood; T15 backward-compat
       keeps both paths working)
    6. screener answers (existing `answer_screeners`)
    7. parse-fidelity validation
    8. keyword coverage validation
    9. ethics pre-flight (verifies bullets-trace-to-profile)

    Returns a BundleResult carrying every stage's output + the audit
    trail dict (which the caller persists to `application.generation_trace`).
    """
    result = BundleResult()
    user_id = application.user_id

    # Pre-flight cost-cap probe — if exhausted, bail without any LLM spend.
    if await dg.is_cost_capped(session, user_id, settings):
        result.skipped_reason = "cost_cap_reached"
        result.degraded = True
        result.degraded_reason = "cost_cap_reached"
        trace = await _initial_trace(settings=settings, corpus=None)
        trace["stages_skipped"] = [
            "corpus",
            "hiring_manager",
            "resume",
            "headline",
            "cover_letter",
            "screeners",
            "parse_fidelity",
            "keyword_coverage",
            "ethics",
        ]
        trace["degraded_mode"] = True
        trace["cost_cap_at_exhaustion"] = float(settings.daily_llm_cost_cap_usd or 0.0)
        result.generation_trace = trace
        await _persist_trace(session, application, trace)
        return result

    # Resolve Job if not passed
    if job is None and application.job_id is not None:
        job = (await session.exec(select(Job).where(Job.id == application.job_id))).one_or_none()
    if job is None:
        raise ValueError(f"application {application.id} has no job context")

    # Stage 1 — corpus
    corpus = await assemble_corpus(session, user_id)
    trace = await _initial_trace(settings=settings, corpus=corpus)
    trace["stages_run"].append("corpus")

    # Stage 2 — hiring manager (regex first; LLM fallback only when JD ≥200)
    if await dg.is_cost_capped(session, user_id, settings):
        result.degraded = True
        result.degraded_reason = "cost_cap_reached"
        trace["degraded_mode"] = True
        trace["cost_cap_at_exhaustion"] = float(settings.daily_llm_cost_cap_usd or 0.0)
        trace["stages_skipped"].extend(
            ["hiring_manager", "resume", "headline", "cover_letter", "screeners"]
        )
        result.generation_trace = trace
        await _persist_trace(session, application, trace)
        return result

    hiring_manager = await extract_hiring_manager(
        session=session,
        user_id=user_id,
        settings=settings,
        job_description=job.description or job.description_html or "",
        application_id=application.id,
        manual_override=hiring_manager_override,
    )
    result.hiring_manager = hiring_manager
    if hiring_manager is not None:
        trace["hiring_manager"] = {
            "name": hiring_manager.name,
            "title": hiring_manager.title,
            "source": hiring_manager.source,
            "confidence": hiring_manager.confidence,
        }
    trace["stages_run"].append("hiring_manager")

    # Stage 3 — resume (delegates to existing pipeline)
    if await dg.is_cost_capped(session, user_id, settings):
        result.degraded = True
        result.degraded_reason = "cost_cap_reached"
        trace["degraded_mode"] = True
        trace["stages_skipped"].extend(["resume", "headline", "cover_letter", "screeners"])
        result.generation_trace = trace
        await _persist_trace(session, application, trace)
        return result

    try:
        resume = await dg.generate_resume(session, application, settings=settings, job=job)
        result.resume = resume
        trace["stages_run"].append("resume")
        if resume.bullet_selection:
            trace["bullet_selections"] = [
                {"bullet_id": bid, "jd_signal": "", "citation": ""}
                for bid in (resume.bullet_selection.get("selected_ids") or [])
            ]
    except dg.CostCapExceededError:
        result.degraded = True
        result.degraded_reason = "cost_cap_reached"
        trace["degraded_mode"] = True
        trace["stages_skipped"].extend(["resume", "headline", "cover_letter", "screeners"])
        result.generation_trace = trace
        await _persist_trace(session, application, trace)
        return result

    # Stage 4 — tailored headline (gated on Job.score ≥ 0.50)
    if await dg.is_cost_capped(session, user_id, settings):
        result.degraded = True
        result.degraded_reason = "cost_cap_reached"
        trace["degraded_mode"] = True
        trace["stages_skipped"].extend(["headline", "cover_letter", "screeners"])
        result.generation_trace = trace
        await _persist_trace(session, application, trace)
        return result

    profile, experiences = await _load_profile_experiences(session, user_id)
    headline = None
    job_score_val = float(getattr(job, "score", 0.0) or 0.0)
    breakdown = getattr(job, "match_breakdown", None) or {}
    matched_tags = list(breakdown.get("matched_tags") or [])
    if profile is not None and job_score_val >= HEADLINE_SCORE_GATE:
        headline = await tailor_headline_for_application(
            session=session,
            user_id=user_id,
            settings=settings,
            profile=profile,
            experiences=experiences,
            job=job,
            job_score=job_score_val,
            matched_tags=matched_tags,
            application_id=application.id,
        )
        if headline is not None:
            trace["headline_used"] = headline.headline_one_line
        trace["stages_run"].append("headline")
    else:
        trace["stages_skipped"].append("headline")

    # Stage 5 — cover letter (delegates to existing pipeline; T15 keeps old path)
    if await dg.is_cost_capped(session, user_id, settings):
        result.degraded = True
        result.degraded_reason = "cost_cap_reached"
        trace["degraded_mode"] = True
        trace["stages_skipped"].extend(["cover_letter", "screeners"])
        result.generation_trace = trace
        await _persist_trace(session, application, trace)
        return result

    try:
        cover = await dg.generate_cover_letter(session, application, settings=settings, job=job)
        result.cover_letter = cover
        trace["stages_run"].append("cover_letter")
    except dg.CostCapExceededError:
        result.degraded = True
        result.degraded_reason = "cost_cap_reached"
        trace["degraded_mode"] = True
        trace["stages_skipped"].extend(["cover_letter", "screeners"])
        result.generation_trace = trace
        await _persist_trace(session, application, trace)
        return result

    # Stage 6 — screeners
    if await dg.is_cost_capped(session, user_id, settings):
        result.degraded = True
        result.degraded_reason = "cost_cap_reached"
        trace["degraded_mode"] = True
        trace["stages_skipped"].append("screeners")
        result.generation_trace = trace
        await _persist_trace(session, application, trace)
        return result

    try:
        screeners = await dg.answer_screeners(session, application, settings=settings, job=job)
        result.screeners = list(screeners)
        trace["stages_run"].append("screeners")
    except dg.CostCapExceededError:
        result.degraded = True
        result.degraded_reason = "cost_cap_reached"
        trace["degraded_mode"] = True
        trace["stages_skipped"].append("screeners")

    # Stage 7 — parse fidelity (cheap; always run)
    if result.resume is not None and result.resume.path:
        try:
            from pathlib import Path

            pdf_path = Path(result.resume.path)
            parse_report = validate_parse_fidelity(
                pdf_path, threshold=settings.parse_fidelity_threshold
            )
            result.parse_fidelity = parse_report
            trace["parse_fidelity_score"] = parse_report.score
            trace["parse_fidelity_tier"] = parse_report.tier
            trace["parse_fidelity_fields_missing"] = [
                k for k, v in parse_report.fields_found.items() if not v
            ]
            trace["stages_run"].append("parse_fidelity")
        except Exception as exc:  # noqa: BLE001
            log.warning("parse_fidelity validation failed: %s", exc)
            trace["stages_skipped"].append("parse_fidelity")

    # Stage 8 — keyword coverage (cheap; always run)
    if result.resume is not None:
        must_haves = _extract_must_haves(job, breakdown)
        resume_text = _resume_text_for_coverage(result.resume)
        cov = compute_coverage(
            must_haves,
            resume_text,
            threshold=settings.parse_fidelity_threshold,
        )
        result.keyword_coverage = cov
        trace["keyword_coverage_score"] = cov.score
        trace["keyword_coverage_missing"] = cov.missing_keywords
        trace["jd_keywords_extracted"] = must_haves
        trace["stages_run"].append("keyword_coverage")

    # Stage 9 — ethics pre-flight (drops fabricated bullets)
    if result.resume is not None and result.resume.bullet_selection:
        # Build the set of legitimate Bullet.id values for this user.
        from models import Bullet

        bullet_ids = {
            int(row[0])
            for row in (
                await session.exec(
                    select(Bullet.id)
                    .join(Experience, Bullet.experience_id == Experience.id)
                    .join(Profile, Experience.profile_id == Profile.id)
                    .where(
                        Profile.user_id == user_id,
                        Profile.deleted_at.is_(None),
                        Experience.deleted_at.is_(None),
                        Bullet.deleted_at.is_(None),
                    )
                )
            ).all()
        }
        selected_ids = list(result.resume.bullet_selection.get("selected_ids") or [])
        trimmed_lines = dict(result.resume.bullet_selection.get("trimmed_lines") or {})
        # Convert keys (some sources serialize int keys as str)
        trimmed_int_keys: dict[int, str] = {
            int(k) if isinstance(k, str) else k: str(v) for k, v in trimmed_lines.items()
        }
        ethics = preflight_check(selected_ids, trimmed_int_keys, bullet_ids)
        result.ethics = ethics
        trace["ethics_pre_flight"] = {
            "passed": ethics.passed,
            "dropped_bullets": ethics.dropped_bullets,
            "flags": ethics.flags,
        }
        trace["stages_run"].append("ethics")

    trace["generated_at"] = datetime.now(UTC).isoformat()
    result.generation_trace = trace
    await _persist_trace(session, application, trace)
    return result
