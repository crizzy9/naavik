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
from pathlib import Path
from typing import Any, Literal

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
from services.ai_tell_blocklist import effective_blocklist, strip_violations
from services.ats_parser_fidelity import (
    ParseScoreReport,
    validate_parse_fidelity,
)
from services.burstiness_check import check_and_score
from services.constitution import render_preamble
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
        # Plan 72 § Surface 2 — per-bullet selection ledger with rationale.
        # Each entry: {bullet_id, selected: bool, why_selected: str|null,
        # why_dropped: str|null}. Drives the inline rationale line under each
        # tailored_bullet_row on Discover · review. Additive to bullet_selections;
        # existing readers of bullet_selections are unaffected.
        "bullet_selection_log": [],
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
    tier: Literal["free", "premium"] | None = None,
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

    Plan 67 (0.3.4) § T8 — `tier` kwarg routes through `_generate_bundle_premium`
    when "premium". Default resolution: explicit kwarg > settings.generation_tier
    > "free". PREMIUM stacks council + detector + critique + tool-loop on top
    of the FREE composite; cost-cap mid-flight gracefully falls back to FREE
    per T9.
    """
    effective_tier = tier or getattr(settings, "generation_tier", "free") or "free"
    if effective_tier == "premium":
        return await _generate_bundle_premium(
            session,
            application,
            settings=settings,
            job=job,
            hiring_manager_override=hiring_manager_override,
        )

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
    user_blocklist = effective_blocklist(corpus.full_text)

    # Constitution preamble (plan 66 § T3) — built lazily on first LLM call
    # so test mocks that skip profile setup still hit the cap-guard path.
    # `_preamble` is None until `_build_preamble` resolves the Profile + the
    # render call; subsequent stages reuse the same string for Anthropic
    # ephemeral cache.
    preamble: str | None = None
    cache_preamble: bool = False
    preamble_built: bool = False

    async def _build_preamble() -> None:
        nonlocal preamble, cache_preamble, preamble_built
        if preamble_built:
            return
        preamble_built = True
        profile_for_preamble, _ = await _load_profile_experiences(session, user_id)
        if profile_for_preamble is not None and corpus.full_text:
            preamble = render_preamble(
                corpus,
                profile_for_preamble.full_name,
                blocklist=user_blocklist,
            )
            cache_preamble = True
        trace["constitution_present"] = cache_preamble

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

    await _build_preamble()
    hiring_manager = await extract_hiring_manager(
        session=session,
        user_id=user_id,
        settings=settings,
        job_description=job.description or job.description_html or "",
        application_id=application.id,
        manual_override=hiring_manager_override,
        system=preamble,
        cache_system=cache_preamble,
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
        resume = await dg.generate_resume(
            session,
            application,
            settings=settings,
            job=job,
            system=preamble,
            cache_system=cache_preamble,
        )
        result.resume = resume
        trace["stages_run"].append("resume")
        if resume.bullet_selection:
            selected_ids = list(resume.bullet_selection.get("selected_ids") or [])
            trace["bullet_selections"] = [
                {"bullet_id": bid, "jd_signal": "", "citation": ""} for bid in selected_ids
            ]
            # Plan 72 § Surface 2 — bullet_selection_log carries the per-bullet
            # rationale shape the Discover · review UI renders. Rationale text
            # is left empty here; the LLM-judge per-bullet "why kept / why
            # dropped" enrichment is deferred to a follow-up plan (the shape is
            # in place so UI consumers don't have to special-case missing keys).
            log_entries: list[dict[str, object]] = []
            seen_ids: set[int] = set()
            for bid in selected_ids:
                try:
                    bid_int = int(bid)
                except (TypeError, ValueError):
                    continue
                if bid_int in seen_ids:
                    continue
                seen_ids.add(bid_int)
                log_entries.append(
                    {
                        "bullet_id": bid_int,
                        "selected": True,
                        "why_selected": None,
                        "why_dropped": None,
                    }
                )
            trace["bullet_selection_log"] = log_entries
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
            system=preamble,
            cache_system=cache_preamble,
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
        hm_payload: dict | None = None
        if hiring_manager is not None:
            hm_payload = {
                "name": hiring_manager.name,
                "title": hiring_manager.title,
                "source": hiring_manager.source,
                "confidence": hiring_manager.confidence,
            }
        cover = await dg.generate_cover_letter(
            session,
            application,
            settings=settings,
            job=job,
            system=preamble,
            cache_system=cache_preamble,
            hiring_manager=hm_payload,
            matched_tags=matched_tags,
        )
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
        screeners = await dg.answer_screeners(
            session,
            application,
            settings=settings,
            job=job,
            system=preamble,
            cache_system=cache_preamble,
        )
        result.screeners = list(screeners)
        trace["stages_run"].append("screeners")
    except dg.CostCapExceededError:
        result.degraded = True
        result.degraded_reason = "cost_cap_reached"
        trace["degraded_mode"] = True
        trace["stages_skipped"].append("screeners")

    # Post-LLM AI-tell strip + burstiness gate (plan 66 § T4 + § T5). The
    # constitution preamble told the LLM not to use blocklisted vocab; this
    # is the second layer that records what slipped through. Both checks
    # run best-effort against in-memory text only — PDF re-render of the
    # scrubbed text is deferred to 0.3.3 follow-up (requires regen path).
    ai_tell_violations: list[str] = []
    if result.resume is not None and result.resume.bullet_selection:
        trimmed = result.resume.bullet_selection.get("trimmed_lines") or {}
        if isinstance(trimmed, dict):
            for value in trimmed.values():
                _, found = strip_violations(str(value), user_blocklist)
                ai_tell_violations.extend(found)
    if result.cover_letter is not None and result.cover_letter.bullet_selection:
        sota = result.cover_letter.bullet_selection
        for key in ("hook", "match", "close", "intro", "body"):
            value = sota.get(key)
            if isinstance(value, str) and value:
                _, found = strip_violations(value, user_blocklist)
                ai_tell_violations.extend(found)
    # Dedupe while preserving order for audit trail readability.
    seen_v: set[str] = set()
    deduped: list[str] = []
    for v in ai_tell_violations:
        if v not in seen_v:
            seen_v.add(v)
            deduped.append(v)
    trace["ai_tell_violations"] = deduped

    # Burstiness — std-dev over trimmed bullet word counts.
    # Plan 75 / 0.3.3.05 — when std-dev < 6 (AI-uniform reading), regen the
    # worst-offender bullet once with explicit variance instruction. Cap at
    # one regen per bundle (mirrors critique-council T4). Cost-cap probe
    # gates the regen LLM call so a runaway burstiness path doesn't
    # exhaust the daily cap.
    if result.resume is not None and result.resume.bullet_selection:
        trimmed = result.resume.bullet_selection.get("trimmed_lines") or {}
        if isinstance(trimmed, dict) and len(trimmed) >= 2:
            # Materialize as list while preserving key order to map idx → key.
            keys: list = list(trimmed.keys())
            values: list[str] = [str(trimmed[k]) for k in keys]
            report = check_and_score(values)
            trace["burstiness_std"] = report.std_dev
            if not report.passed and report.worst_offender_idx is not None:
                trace["burstiness_std_pre_regen"] = report.std_dev
                worst_idx = report.worst_offender_idx
                if await dg.is_cost_capped(session, user_id, settings):
                    trace["burstiness_regen_skipped_cost_cap"] = True
                else:
                    worst_key = keys[worst_idx]
                    regen_text = await dg.regen_bullet_for_variance(
                        session=session,
                        settings=settings,
                        user_id=user_id,
                        application_id=application.id,
                        original_text=values[worst_idx],
                        target=report.suggested_target,
                        target_words=report.suggested_target_words,
                        system=preamble,
                        cache_system=cache_preamble,
                    )
                    # Plan 85 / 0.3.3.24 — when the helper swallows an
                    # `LLMProviderError` it returns the unchanged original
                    # (same text, same length). Record the failure shape
                    # in the audit trail so a debugger reading a
                    # degraded-looking trace can tell "regen attempted but
                    # failed" apart from the legitimate no-substitution
                    # branch (regen ran but returned identical text).
                    if not regen_text or regen_text == values[worst_idx]:
                        trace["burstiness_regen_failed"] = True
                    else:
                        # Substitute + recompute. Hard cap = 1 regen per bundle.
                        trimmed[worst_key] = regen_text
                        values[worst_idx] = regen_text
                        result.resume.bullet_selection["trimmed_lines"] = trimmed
                        post_report = check_and_score(values)
                        trace["burstiness_std"] = post_report.std_dev
                        if not post_report.passed:
                            trace["burstiness_regen_insufficient"] = True

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


# ── PREMIUM tier dispatch (plan 67 / 0.3.4 § T8) ──────────────────────────


async def _generate_bundle_premium(
    session: AsyncSession,
    application: Application,
    *,
    settings: Settings,
    job: Job | None = None,
    hiring_manager_override: str | None = None,
) -> BundleResult:
    """PREMIUM-tier branch. Stacks council + detector + critique + tool-loop
    on top of the FREE composite per plan 67 § T8.

    Flow:
      1. Run FREE pipeline (corpus -> hiring_manager -> resume -> headline
         -> cover -> screeners -> parse_fidelity -> keyword_coverage -> ethics)
         to materialize the bundle.
      2. PREMIUM stages stacked on top, each cost-cap guarded:
         - council (bullet-selection) -> recorded but not re-applied (the FREE
           pipeline's select already ran; council audit-trail surfaces the
           heterogeneous ranking signal for the user)
         - detector_loop on resume bullets + cover letter
         - critique_council on rendered text (may flag regen-needed; we DON'T
           regen mid-flight per T4 — caller surfaces concerns to the user)
         - tool_loop orchestrator
      3. Trace records all PREMIUM keys per T10 + degraded_mode + stages skipped.

    Cost-cap behavior (T9): when the cap fires AFTER FREE completes but BEFORE
    a PREMIUM stage, that stage and downstream stages skip; trace marks
    `degraded_mode=True` with `degraded_reason="cost_cap_reached_premium"`.
    The FREE composite still ships.
    """
    # Lazy-import the PREMIUM machinery so FREE callers don't pay the import
    # cost (council pulls Anthropic batch; detector pulls Originality).
    from services.ats_parser_ensemble import ensemble_score
    from services.council import vote_on_bullet_selection
    from services.critique_council import critique_bundle
    from services.detector_loop import run_detector_loop
    from services.tool_loop import orchestrate_refinement

    # First run the FREE composite (recursive call with explicit tier="free"
    # to avoid infinite loop). This handles cost-cap pre-flight + the 9-stage
    # FREE flow + ethics + parse_fidelity + keyword_coverage.
    free_result = await generate_bundle(
        session,
        application,
        settings=settings,
        job=job,
        hiring_manager_override=hiring_manager_override,
        tier="free",
    )

    trace = dict(free_result.generation_trace or {})
    trace["tier"] = "premium"
    trace.setdefault("premium_stages_completed", [])
    trace.setdefault("premium_stages_skipped", [])

    # When FREE itself bailed pre-flight (cost cap), don't try PREMIUM.
    if free_result.skipped_reason is not None:
        free_result.generation_trace = trace
        await _persist_trace(session, application, trace)
        return free_result

    user_id = application.user_id

    # Resolve Job for downstream stages.
    if job is None and application.job_id is not None:
        job = (await session.exec(select(Job).where(Job.id == application.job_id))).one_or_none()
    job_desc = ""
    job_role = ""
    job_must_haves: list[str] = []
    if job is not None:
        job_desc = job.description or job.description_html or ""
        job_role = job.role or ""
        breakdown = getattr(job, "match_breakdown", None) or {}
        job_must_haves = _extract_must_haves(job, breakdown)

    # Constitution preamble — rebuilt locally so PREMIUM stages get the same
    # cache-friendly system message that FREE stages used.
    user_blocklist: set[str] = set()
    preamble: str | None = None
    cache_preamble: bool = False
    try:
        corpus = await assemble_corpus(session, user_id)
        if corpus and corpus.full_text:
            user_blocklist = effective_blocklist(corpus.full_text)
            profile_row, _ = await _load_profile_experiences(session, user_id)
            if profile_row is not None:
                preamble = render_preamble(
                    corpus,
                    profile_row.full_name,
                    blocklist=user_blocklist,
                )
                cache_preamble = True
    except Exception as exc:  # noqa: BLE001 — preamble is opportunistic
        log.debug("PREMIUM preamble rebuild failed (non-fatal): %s", exc)

    # PREMIUM stage 1 — bullet-selection council
    if await dg.is_cost_capped(session, user_id, settings):
        trace["premium_stages_skipped"].extend(["council", "detector", "critique", "tool_loop"])
        trace["degraded_mode"] = True
        trace["degraded_reason"] = "cost_cap_reached_premium"
        free_result.degraded = True
        free_result.degraded_reason = "cost_cap_reached_premium"
        free_result.generation_trace = trace
        await _persist_trace(session, application, trace)
        return free_result

    candidate_bullets: list[dict] = []
    if free_result.resume is not None and free_result.resume.bullet_selection:
        # The FREE pipeline already picked + trimmed bullets; council ranks
        # over the SAME set so the audit trail captures persona disagreement
        # without re-rendering the resume mid-flight.
        ids = list(free_result.resume.bullet_selection.get("selected_ids") or [])
        trimmed = free_result.resume.bullet_selection.get("trimmed_lines") or {}
        for bid in ids:
            text = trimmed.get(str(bid)) or trimmed.get(bid) or ""
            if text:
                candidate_bullets.append({"id": int(bid), "text": str(text)})

    if candidate_bullets:
        try:
            council_report = await vote_on_bullet_selection(
                candidate_bullets,
                {
                    "role": job_role,
                    "description": job_desc,
                    "skills_required": (job.skills_required if job else []) or [],
                    "company": (job.company if job else ""),
                },
                session=session,
                user_id=user_id,
                settings=settings,
                application_id=application.id,
                system=preamble,
                cache_system=cache_preamble,
                top_k=min(8, len(candidate_bullets)),
            )
            trace["council_votes"] = council_report.persona_rankings
            trace["council_borda_scores"] = {
                str(k): v for k, v in council_report.borda_scores.items()
            }
            trace["council_selected_ids"] = council_report.selected_ids
            trace["premium_stages_completed"].append("council")
        except Exception as exc:  # noqa: BLE001
            log.warning("council stage failed: %s", exc)
            trace["premium_stages_skipped"].append("council")
    else:
        trace["premium_stages_skipped"].append("council")

    # PREMIUM stage 2 — detector loop on resume bullets + cover letter
    if await dg.is_cost_capped(session, user_id, settings):
        trace["premium_stages_skipped"].extend(["detector", "critique", "tool_loop"])
        trace["degraded_mode"] = True
        trace["degraded_reason"] = "cost_cap_reached_premium"
        free_result.degraded = True
        free_result.degraded_reason = "cost_cap_reached_premium"
        free_result.generation_trace = trace
        await _persist_trace(session, application, trace)
        return free_result

    resume_text = _resume_text_for_coverage(free_result.resume)
    cover_text = ""
    if free_result.cover_letter is not None and free_result.cover_letter.bullet_selection:
        sota = free_result.cover_letter.bullet_selection
        for key in ("hook", "match", "close", "intro", "body"):
            value = sota.get(key)
            if isinstance(value, str) and value:
                cover_text += value + "\n"

    detector_input = (resume_text + "\n\n" + cover_text).strip()
    if detector_input:
        try:
            detector_report = await run_detector_loop(
                detector_input,
                session=session,
                user_id=user_id,
                settings=settings,
                application_id=application.id,
                system=preamble,
                cache_system=cache_preamble,
            )
            trace["detector_iterations"] = [
                {
                    "iter_n": it.iter_n,
                    "confidence": it.confidence,
                    "refinements": it.refinements,
                    "flagged_phrases": it.flagged_phrases,
                }
                for it in detector_report.iterations
            ]
            trace["detector_final_confidence"] = detector_report.final_confidence
            trace["detector_target_met"] = detector_report.target_met
            trace["originality_score"] = detector_report.originality_score
            trace["premium_stages_completed"].append("detector")
        except Exception as exc:  # noqa: BLE001
            log.warning("detector stage failed: %s", exc)
            trace["premium_stages_skipped"].append("detector")
    else:
        trace["premium_stages_skipped"].append("detector")

    # PREMIUM stage 2.5 — ATS parser ensemble cross-check (plan 67 § T6).
    # Local-CPU only (pdfplumber + optional pyresparser + optional Node
    # subprocess) — no LLM spend, no cost-cap probe needed. Records the
    # aggregate score + parsers used; sub-threshold surfaces as a warning
    # in the audit trail (regen deferred to a follow-up user motion).
    resume_pdf_path: Path | None = None
    if free_result.resume is not None and free_result.resume.path:
        resume_pdf_path = Path(free_result.resume.path)
    if resume_pdf_path is not None and resume_pdf_path.exists():
        try:
            ensemble_report = await ensemble_score(
                resume_pdf_path,
                threshold=settings.parse_fidelity_threshold,
            )
            trace["ensemble_parse_score"] = ensemble_report.aggregate_score
            trace["ensemble_parsers_used"] = list(ensemble_report.parsers_used)
            trace["ensemble_below_threshold"] = (
                ensemble_report.aggregate_score < settings.parse_fidelity_threshold
            )
            trace["premium_stages_completed"].append("ensemble")
        except Exception as exc:  # noqa: BLE001
            log.warning("ensemble stage failed: %s", exc)
            trace["premium_stages_skipped"].append("ensemble")
    else:
        trace["premium_stages_skipped"].append("ensemble")

    # PREMIUM stage 3 — critique council
    if await dg.is_cost_capped(session, user_id, settings):
        trace["premium_stages_skipped"].extend(["critique", "tool_loop"])
        trace["degraded_mode"] = True
        trace["degraded_reason"] = "cost_cap_reached_premium"
        free_result.degraded = True
        free_result.degraded_reason = "cost_cap_reached_premium"
        free_result.generation_trace = trace
        await _persist_trace(session, application, trace)
        return free_result

    if resume_text or cover_text:
        try:
            critique_report = await critique_bundle(
                resume_text=resume_text,
                cover_letter_text=cover_text,
                job_desc=job_desc,
                session=session,
                user_id=user_id,
                settings=settings,
                application_id=application.id,
                system=preamble,
                cache_system=cache_preamble,
            )
            trace["critique_persona_feedback"] = critique_report.persona_votes
            trace["critique_consensus_concerns"] = critique_report.consensus_concerns
            trace["critique_recommendation_tally"] = critique_report.recommendation_tally
            trace["critique_majority_recommendation"] = critique_report.majority_recommendation
            trace["critique_should_regenerate"] = critique_report.should_regenerate
            trace["critique_regeneration_triggered"] = False  # T4: capped at 0 mid-flight
            trace["premium_stages_completed"].append("critique")
        except Exception as exc:  # noqa: BLE001
            log.warning("critique stage failed: %s", exc)
            trace["premium_stages_skipped"].append("critique")
    else:
        trace["premium_stages_skipped"].append("critique")

    # PREMIUM stage 4 — tool-loop orchestrator
    if await dg.is_cost_capped(session, user_id, settings):
        trace["premium_stages_skipped"].append("tool_loop")
        trace["degraded_mode"] = True
        trace["degraded_reason"] = "cost_cap_reached_premium"
        free_result.degraded = True
        free_result.degraded_reason = "cost_cap_reached_premium"
        free_result.generation_trace = trace
        await _persist_trace(session, application, trace)
        return free_result

    if free_result.resume is not None:
        # Resolve profile bullet ids for the defensibility tool.
        from models import Bullet

        try:
            profile_bullet_rows = (
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
            profile_bullet_ids: set[int] = set()
            for row in profile_bullet_rows:
                bid = row[0] if isinstance(row, tuple) else row
                profile_bullet_ids.add(int(bid))
        except Exception as exc:  # noqa: BLE001
            log.debug("profile bullet id lookup failed for tool_loop: %s", exc)
            profile_bullet_ids = set()

        selected_ids = (
            list(free_result.resume.bullet_selection.get("selected_ids") or [])
            if free_result.resume.bullet_selection
            else []
        )
        resume_pdf_path = Path(free_result.resume.path) if free_result.resume.path else None

        try:
            tool_report = await orchestrate_refinement(
                resume_text=resume_text,
                cover_letter_text=cover_text,
                resume_pdf_path=resume_pdf_path,
                job_role=job_role,
                job_must_haves=job_must_haves,
                selected_bullet_ids=selected_ids,
                profile_bullet_ids=profile_bullet_ids,
                settings=settings,
                user_id=user_id,
                session=session,
                application_id=application.id,
                system=preamble,
                cache_system=cache_preamble,
            )
            trace["tool_loop_iterations"] = [
                {
                    "iter_n": it.iter_n,
                    "tool_calls": [
                        {
                            "name": tc.name,
                            "input": tc.input,
                            "result_summary": tc.result_summary,
                        }
                        for tc in it.tool_calls
                    ],
                    "decision": it.decision,
                    "cost_usd": it.cost_usd,
                }
                for it in tool_report.iterations
            ]
            trace["tool_loop_final_decision"] = tool_report.final_decision
            trace["premium_stages_completed"].append("tool_loop")
        except Exception as exc:  # noqa: BLE001
            log.warning("tool_loop stage failed: %s", exc)
            trace["premium_stages_skipped"].append("tool_loop")
    else:
        trace["premium_stages_skipped"].append("tool_loop")

    trace["generated_at"] = datetime.now(UTC).isoformat()
    free_result.generation_trace = trace
    await _persist_trace(session, application, trace)
    return free_result
