"""Bundle orchestration — BundleResult + the FREE composite + cover-letter regen.

Split out of the former services/bundle_generator.py in plan 91 Phase 4.4;
behaviour unchanged. Cross-seam calls
(`is_cost_capped`, `generate_resume`, `generate_cover_letter`,
`answer_screeners`, `regen_bullet_for_variance`, and the bundle composites)
route through the `services.generation` package surface at call time
(`svc()` / `_bg()`) so `patch("services.generation.X")` keeps intercepting.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
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
from services.generation.ai_tell_blocklist import effective_blocklist, strip_violations
from services.generation.ats_parser_fidelity import (
    ParseScoreReport,
)
from services.generation.burstiness_check import check_and_score
from services.generation.common import svc
from services.generation.constitution import render_preamble
from services.generation.cost_cap import CostCapExceededError
from services.generation.ethics_preflight import EthicsReport, preflight_check
from services.generation.hiring_manager_extractor import HiringManagerHit
from services.generation.keyword_coverage import CoverageReport, compute_coverage
from services.generation.trace import (
    _initial_trace,
    _persist_trace,
)

log = logging.getLogger(__name__)


def _bg():
    """The `services.generation` package surface, resolved at call time —
    keeps patch("services.generation.{assemble_corpus,
    extract_hiring_manager,_load_profile_experiences,generate_bundle}")
    intercepting internal calls."""
    from services import generation

    return generation


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


async def regenerate_cover_letter(
    session: AsyncSession,
    application: Application,
    *,
    settings: Settings,
    hiring_manager_override: str | None = None,
) -> BundleResult:
    """Re-render ONLY the cover letter for `application` (plan 86 R1 round 2).

    Short-circuits the full bundle pipeline: no resume regen, no bullet
    selection re-run, no screener answers. Re-runs corpus assembly +
    hiring manager extraction (cheap, needed for cover-letter inputs)
    then `generate_cover_letter`.

    Returns a `BundleResult` carrying only the new cover letter; resume +
    screeners are left as None (caller handles via response shape — the
    `/api/v1/applications/{id}/generate-bundle` route checks `resume_id`
    for null and surfaces only the cover_letter_id).
    """
    result = BundleResult()
    user_id = application.user_id

    if await svc().is_cost_capped(session, user_id, settings):
        result.skipped_reason = "cost_cap_reached"
        result.degraded = True
        result.degraded_reason = "cost_cap_reached"
        return result

    if application.job_id is None:
        raise ValueError(f"application {application.id} has no job context")
    job = (await session.exec(select(Job).where(Job.id == application.job_id))).one_or_none()
    if job is None:
        raise ValueError(f"application {application.id} has no job context")

    corpus = await _bg().assemble_corpus(session, user_id)
    user_blocklist = effective_blocklist(corpus.full_text) if corpus else set()
    profile_for_preamble, _ = await _bg()._load_profile_experiences(session, user_id)
    preamble: str | None = None
    cache_preamble = False
    if profile_for_preamble is not None and corpus and corpus.full_text:
        preamble = render_preamble(
            corpus,
            profile_for_preamble.full_name,
            blocklist=user_blocklist,
        )
        cache_preamble = True

    hiring_manager = await _bg().extract_hiring_manager(
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

    hm_payload: dict | None = None
    if hiring_manager is not None:
        hm_payload = {
            "name": hiring_manager.name,
            "title": hiring_manager.title,
            "source": hiring_manager.source,
            "confidence": hiring_manager.confidence,
        }

    breakdown = getattr(job, "match_breakdown", None) or {}
    matched_tags = list(breakdown.get("matched_tags") or [])

    try:
        cover = await svc().generate_cover_letter(
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
    except CostCapExceededError:
        result.degraded = True
        result.degraded_reason = "cost_cap_reached"
    return result


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
    4. (headline stage retired 2026-07 — the resume header is name +
       one contact line only; `trace["headline_used"]` stays None)
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
        return await _bg()._generate_bundle_premium(
            session,
            application,
            settings=settings,
            job=job,
            hiring_manager_override=hiring_manager_override,
        )

    result = BundleResult()
    user_id = application.user_id

    # Pre-flight cost-cap probe — if exhausted, bail without any LLM spend.
    if await svc().is_cost_capped(session, user_id, settings):
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
    corpus = await _bg().assemble_corpus(session, user_id)
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
        profile_for_preamble, _ = await _bg()._load_profile_experiences(session, user_id)
        if profile_for_preamble is not None and corpus.full_text:
            preamble = render_preamble(
                corpus,
                profile_for_preamble.full_name,
                blocklist=user_blocklist,
            )
            cache_preamble = True
        trace["constitution_present"] = cache_preamble

    # Stage 2 — hiring manager (regex first; LLM fallback only when JD ≥200)
    if await svc().is_cost_capped(session, user_id, settings):
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
    hiring_manager = await _bg().extract_hiring_manager(
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

    # Stage 3 (headline) RETIRED — item 2 (2026-07): the resume header is
    # name + one contact line, nothing else. `trace["headline_used"]` stays
    # in the trace shape (always None) so older trace consumers don't
    # special-case a missing key. `matched_tags` survives — the cover
    # letter stage grounds on it.
    trace["stages_skipped"].append("headline")
    breakdown = getattr(job, "match_breakdown", None) or {}
    matched_tags = list(breakdown.get("matched_tags") or [])

    # Stage 4 — resume (delegates to existing pipeline)
    if await svc().is_cost_capped(session, user_id, settings):
        result.degraded = True
        result.degraded_reason = "cost_cap_reached"
        trace["degraded_mode"] = True
        trace["stages_skipped"].extend(["resume", "cover_letter", "screeners"])
        result.generation_trace = trace
        await _persist_trace(session, application, trace)
        return result

    try:
        resume = await svc().generate_resume(
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
    except CostCapExceededError:
        result.degraded = True
        result.degraded_reason = "cost_cap_reached"
        trace["degraded_mode"] = True
        trace["stages_skipped"].extend(["resume", "headline", "cover_letter", "screeners"])
        result.generation_trace = trace
        await _persist_trace(session, application, trace)
        return result

    # Stage 5 — cover letter (delegates to existing pipeline; T15 keeps old path)
    if await svc().is_cost_capped(session, user_id, settings):
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
        cover = await svc().generate_cover_letter(
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
    except CostCapExceededError:
        result.degraded = True
        result.degraded_reason = "cost_cap_reached"
        trace["degraded_mode"] = True
        trace["stages_skipped"].extend(["cover_letter", "screeners"])
        result.generation_trace = trace
        await _persist_trace(session, application, trace)
        return result

    # Stage 6 — screeners
    if await svc().is_cost_capped(session, user_id, settings):
        result.degraded = True
        result.degraded_reason = "cost_cap_reached"
        trace["degraded_mode"] = True
        trace["stages_skipped"].append("screeners")
        result.generation_trace = trace
        await _persist_trace(session, application, trace)
        return result

    try:
        screeners = await svc().answer_screeners(
            session,
            application,
            settings=settings,
            job=job,
            system=preamble,
            cache_system=cache_preamble,
        )
        result.screeners = list(screeners)
        trace["stages_run"].append("screeners")
    except CostCapExceededError:
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
                if await svc().is_cost_capped(session, user_id, settings):
                    trace["burstiness_regen_skipped_cost_cap"] = True
                else:
                    worst_key = keys[worst_idx]
                    regen_text = await svc().regen_bullet_for_variance(
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
            parse_report = _bg().validate_parse_fidelity(
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

        # SQLModel's exec() yields scalars for single-column selects (and
        # tuples on some legacy paths) — `row[0]` on an int crashed every
        # real bundle generation at the ethics stage (live-verify find).
        bullet_ids = {
            int(row[0] if isinstance(row, tuple) else row)
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

    # Stage 10 — evaluation scorecard (item 9, 2026-07). Deterministic
    # checks are free; the judge is ONE tracked call, skipped when no
    # provider or the cost cap is exhausted. Never blocks the bundle.
    if result.resume is not None:
        from services.generation import generation_eval

        try:
            run_judge = not await svc().is_cost_capped(session, user_id, settings)
            scorecard = await generation_eval.evaluate_bundle(
                session, application, settings=settings, run_judge=run_judge
            )
            if scorecard is not None:
                trace["eval_scorecard"] = scorecard
                trace["stages_run"].append("eval")
        except Exception as exc:  # noqa: BLE001 — eval is observability, not gating
            log.warning("bundle eval failed: %s", exc)
            trace["stages_skipped"].append("eval")

    trace["generated_at"] = datetime.now(UTC).isoformat()
    result.generation_trace = trace
    await _persist_trace(session, application, trace)
    return result
