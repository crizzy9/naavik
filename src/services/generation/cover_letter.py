"""SOTA cover-letter generation (adaptive format dispatch).

Split out of the former services/document_generator.py in plan 91 Phase 4.3;
behaviour unchanged. Internal calls to patched seams go through `svc()`
(the facade) so test interception keeps working.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from llm import LLMProviderError
from models import (
    Application,
    GeneratedDocument,
    GeneratedDocumentKind,
    Job,
    Settings,
)
from services.generation.common import svc
from services.generation.cost_cap import CostCapExceededError
from services.generation.snapshot import _bullet_inventory, _latest_resume
from typst.compiler import TypstError

log = logging.getLogger(__name__)


async def generate_cover_letter(
    session: AsyncSession,
    application: Application,
    *,
    settings: Settings,
    job: Job | None = None,
    tone: str = "enthusiastic",
    system: str | None = None,
    cache_system: bool = False,
    hiring_manager: dict | None = None,
    matched_tags: list[str] | None = None,
) -> GeneratedDocument:
    """Generate a SOTA cover letter (plan 66 § T10).

    Uses `draft_cover_letter_sota` w/ adaptive format dispatch (pain-letter
    vs standard) via `tracked_call` so `ApiUsage` rows persist for cost
    tracking. `system` + `cache_system` thread the voice-grounded
    constitution preamble; `hiring_manager` + `matched_tags` come from the
    bundle orchestrator's stage-2 extraction + JobScore.
    """
    user_id = application.user_id
    if await svc().is_cost_capped(session, user_id, settings):
        raise CostCapExceededError("daily_llm_cost_cap_usd reached")

    snap = await svc().load_profile_snapshot(session, user_id)
    if snap is None:
        raise ValueError(f"no profile for user_id={user_id}")
    if job is None and application.job_id is not None:
        job = (await session.exec(select(Job).where(Job.id == application.job_id))).one_or_none()
    if job is None:
        raise ValueError(f"application {application.id} has no job context")

    from llm.prompts.draft_cover_letter_sota import (
        CoverLetterSota,
        detect_pain_letter_format,
    )

    # Adaptive format dispatch — honor Settings.cover_letter_format override.
    cover_letter_format_setting = getattr(settings, "cover_letter_format", "auto")
    job_description = job.description or job.description_html or ""
    if cover_letter_format_setting == "pain_letter":
        format_chosen = "pain_letter"
    elif cover_letter_format_setting == "standard":
        format_chosen = "standard"
    else:
        format_chosen = "pain_letter" if detect_pain_letter_format(job_description) else "standard"

    provider = svc().get_provider(settings)
    # Voice-first raw material: the letter must be built from the OWNER's
    # words, ordered by JD relevance — not the first 10 bullets in profile
    # order. The resume pass (which runs first in the bundle) already ranked
    # the full inventory against this JD; reuse that ranking on the ORIGINAL
    # bullet texts (originals carry the owner's voice; trimmed lines are
    # JD-mirrored rewrites).
    inventory = _bullet_inventory(snap)
    ranked_ids: list[int] = []
    try:
        latest_resume = await _latest_resume(session, application.id)
        selection = getattr(latest_resume, "bullet_selection", None)
        if isinstance(selection, dict):
            raw_ranked = selection.get("ranked_ids") or []
            ranked_ids = [i for i in raw_ranked if isinstance(i, int)]
    except Exception:  # noqa: BLE001 — ranking is a nice-to-have, never fatal
        ranked_ids = []
    by_id = {b.id: b for b in inventory}
    ordered = [by_id[i] for i in ranked_ids if i in by_id]
    ranked_set = set(ranked_ids)
    ordered += [b for b in inventory if b.id not in ranked_set]
    top_bullets = [b.text for b in ordered[:10]]
    profile_payload = {
        "full_name": snap.profile.full_name,
        # summary_full is the owner-written master — the strongest voice
        # sample we have. summary_short is an AI condensation; last resort.
        "summary": snap.profile.summary_full or snap.profile.summary_short or "",
        "top_bullets": top_bullets,
    }
    job_payload = {
        "company": job.company,
        "role": job.role,
        "description": job_description,
    }
    try:
        result = await svc().llm_tracker.tracked_call(
            session=session,
            user_id=user_id,
            provider=provider,
            method="structured",
            prompt_name="draft_cover_letter_sota",
            application_id=application.id,
            prompt=_render_cover_letter_sota_prompt(
                profile_payload, job_payload, matched_tags or [], hiring_manager, format_chosen
            ),
            schema=CoverLetterSota,
            system=system,
            cache_system=cache_system,
        )
        sota_value = result.value
        # CoverLetterSota → cover_letter.typ payload shape (T10 mapping).
        # hook → intro; match → body; why_company + close map 1:1.
        letter_dict = {
            "intro": str(sota_value.get("hook", "")),
            "body": str(sota_value.get("match", "")),
            "why_company": str(sota_value.get("why_company", "")),
            "close": str(sota_value.get("close", "")),
            "_sota_format_chosen": str(sota_value.get("format_chosen", format_chosen)),
            "_sota_verbatim_phrases": list(sota_value.get("verbatim_phrases", []) or []),
            "_sota_hiring_manager_used": dict(sota_value.get("hiring_manager_used", {}) or {}),
        }
    except LLMProviderError as exc:
        log.warning("cover letter draft failed; using template: %s", exc)
        letter_dict = {
            "intro": f"I'm applying for the {job.role} role at {job.company}.",
            "body": snap.profile.summary_full or snap.profile.summary_short or "",
            "why_company": "The work described in this posting is the kind I want to do next.",
            "close": "I'd like to talk about how I can help.",
        }

    out_dir = svc()._app_documents_dir(application.id)
    out_pdf = out_dir / "cover-letter.pdf"

    today_str = datetime.now(UTC).strftime("%B %-d, %Y")

    # Strip the SOTA-only audit fields before passing to Typst (typst template
    # only consumes {intro, body, why_company, close}).
    typst_letter = {k: v for k, v in letter_dict.items() if not k.startswith("_sota_")}

    # Recipient block + greeting — a real letter addresses a person when we
    # know one (hiring-manager extraction, confidence-gated).
    recipient_name = None
    recipient_title = None
    if hiring_manager and hiring_manager.get("name"):
        confidence = float(hiring_manager.get("confidence") or 0.0)
        if confidence >= 0.5:
            recipient_name = str(hiring_manager["name"])
            recipient_title = hiring_manager.get("title")
    greeting = f"Dear {recipient_name}," if recipient_name else "Dear Hiring Team,"

    typst_data = {
        "profile": {
            "full_name": snap.profile.full_name,
            "email": snap.profile.email,
            "phone": snap.profile.phone,
            "location": snap.profile.location,
        },
        "job": {"company": job.company, "role": job.role},
        "recipient": {"name": recipient_name, "title": recipient_title},
        "greeting": greeting,
        "letter": typst_letter,
        "today": today_str,
    }
    try:
        compile_result = await svc().typst_compile("cover_letter", typst_data, out_pdf)
    except TypstError as exc:
        doc = GeneratedDocument(
            application_id=application.id,
            kind=GeneratedDocumentKind.COVER_LETTER,
            path=str(out_pdf),
            byte_size=0,
            page_count=None,
            compiled_at=datetime.now(UTC),
            model=settings.llm_model,
            error=str(exc),
        )
        session.add(doc)
        await session.flush()
        return doc

    # Stash SOTA audit fields in `bullet_selection` JSONB (opaque blob pattern).
    sota_meta = {
        k.removeprefix("_sota_"): v for k, v in letter_dict.items() if k.startswith("_sota_")
    }
    # Persist the rendered section text so the Discover review workspace can
    # display the ACTUAL generated cover letter (it previously fell back to a
    # hardcoded Intuit/Stripe placeholder because the section text lived only
    # inside the compiled PDF). Stored under `sections` in the same JSONB blob.
    blob: dict[str, Any] = dict(sota_meta)
    blob["sections"] = {
        "intro": str(typst_letter.get("intro", "")),
        "body": str(typst_letter.get("body", "")),
        "why_company": str(typst_letter.get("why_company", "")),
        "close": str(typst_letter.get("close", "")),
    }
    doc = GeneratedDocument(
        application_id=application.id,
        kind=GeneratedDocumentKind.COVER_LETTER,
        path=str(out_pdf),
        byte_size=compile_result.byte_size,
        page_count=compile_result.page_count,
        compiled_at=compile_result.compiled_at,
        model=settings.llm_model,
        bullet_selection=blob,
    )
    session.add(doc)
    await session.flush()
    return doc


def _render_cover_letter_sota_prompt(
    profile: dict,
    job: dict,
    matched_tags: list[str],
    hiring_manager: dict | None,
    format_chosen: str,
) -> str:
    """Render the SOTA cover-letter user message — mirrors `draft_cover_letter_sota.PROMPT_*`.

    Kept in document_generator so the tracked_call entry point uses the same
    text the direct `draft_cover_letter_sota` function would produce; that
    function exists for direct callers (tests) and bypasses tracked_call by
    design.
    """
    from llm.prompts.draft_cover_letter_sota import (
        _PAIN_POINT_RE,
        PROMPT_PAIN_LETTER,
        PROMPT_STANDARD,
    )

    hm_str = "(no specific hiring manager identified)"
    if hiring_manager and hiring_manager.get("name"):
        hm_str = str(hiring_manager["name"])
        if hiring_manager.get("title"):
            hm_str += f", {hiring_manager['title']}"

    top_bullets = profile.get("top_bullets") or []
    bullet_lines = "\n".join(f"- {t}" for t in top_bullets)[:1800]
    profile_str = (
        f"{profile.get('full_name', '')}\n\n"
        f"In their own words — verbatim writing samples; reuse this phrasing:\n"
        f"Summary: {profile.get('summary') or profile.get('summary_short') or profile.get('summary_full') or '(none)'}\n"
        f"Bullets (most relevant to this JD first):\n{bullet_lines}"
    )
    job_str = (
        f"{job.get('company', '')} — {job.get('role', '')}\n{(job.get('description') or '')[:1500]}"
    )

    kwargs = {
        "profile": profile_str,
        "job": job_str,
        "hiring_manager": hm_str,
        "matched_tags": ", ".join(matched_tags),
        "company": job.get("company", ""),
        "name": profile.get("full_name", ""),
    }
    if format_chosen == "pain_letter":
        kwargs["pain_signals"] = ", ".join(_PAIN_POINT_RE.findall(job.get("description", ""))[:5])
        return PROMPT_PAIN_LETTER.format(**kwargs)
    return PROMPT_STANDARD.format(**kwargs)


def _render_cover_letter_prompt(profile: dict, job: dict, tone: str) -> str:
    return (
        f"Draft a cover letter for this candidate × job pair.\n\n"
        f"Candidate:\n{profile.get('full_name', '')}\n"
        f"{profile.get('summary_short') or ''}\n\n"
        f"Job:\n{job['company']} — {job['role']}\n"
        f"{job['description'][:1500]}\n\n"
        f"Tone: {tone}\n\n"
        "Return CoverLetterDraft with intro, body, why_company, close. "
        "Each section 2–4 sentences referencing specific achievements + the company."
    )
