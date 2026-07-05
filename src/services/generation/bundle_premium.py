"""PREMIUM-tier bundle pipeline (council/detector/critique/tool-loop stack).

Split out of services/bundle_generator.py in plan 91 Phase 4.4;
behaviour unchanged. `dg` binds the services.document_generator facade,
so `patch("services.bundle_generator.dg.X")` (which mutates that shared
module object) keeps intercepting; the premium pipeline calls the free
composite through the bundle facade for the same reason.
"""

import logging
from datetime import UTC, datetime
from pathlib import Path

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import (
    Application,
    Experience,
    Job,
    Profile,
    Settings,
)
from services import document_generator as dg
from services.ai_tell_blocklist import effective_blocklist
from services.constitution import render_preamble
from services.generation.bundle import (
    BundleResult,
    _extract_must_haves,
    _resume_text_for_coverage,
)
from services.generation.trace import _persist_trace

log = logging.getLogger(__name__)


def _bg():
    """The `services.bundle_generator` facade, resolved at call time —
    keeps patch("services.bundle_generator.{assemble_corpus,
    extract_hiring_manager,_load_profile_experiences,generate_bundle}")
    intercepting internal calls."""
    from services import bundle_generator

    return bundle_generator


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
    free_result = await _bg().generate_bundle(
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
        corpus = await _bg().assemble_corpus(session, user_id)
        if corpus and corpus.full_text:
            user_blocklist = effective_blocklist(corpus.full_text)
            profile_row, _ = await _bg()._load_profile_experiences(session, user_id)
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
