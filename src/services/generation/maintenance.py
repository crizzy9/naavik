"""Workspace recompiles (LLM-free), composite pre_generate, stale-doc cleanup cron.

Split out of the former services/document_generator.py in plan 91 Phase 4.3;
behaviour unchanged. Internal calls to patched seams go through `svc()`
(the facade) so test interception keeps working.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import (
    Application,
    ApplicationScreenerAnswer,
    GeneratedDocument,
    GeneratedDocumentKind,
    Job,
    Settings,
)
from models.enums import BulletSelectionOverride
from services.generation.common import _select_template, svc
from services.generation.resume import (
    _application_bullet_overrides,
    _build_resume_data,
)
from services.generation.snapshot import _bullet_inventory

log = logging.getLogger(__name__)


def _application_text_overrides(application: Application) -> dict[int, str]:
    """Per-app bullet TEXT overrides from `submission_artifacts` — the
    workspace's 'edit this line for this application' storage."""
    artifacts = getattr(application, "submission_artifacts", None) or {}
    raw = artifacts.get("bullet_text_overrides") if isinstance(artifacts, dict) else None
    if not isinstance(raw, dict):
        return {}
    out: dict[int, str] = {}
    for key, value in raw.items():
        if not isinstance(value, str) or not value.strip():
            continue
        try:
            out[int(key)] = value.strip()
        except (TypeError, ValueError):
            continue
    return out


async def _latest_error_free_doc(
    session: AsyncSession, application_id: int, kind: GeneratedDocumentKind
) -> GeneratedDocument | None:
    return (
        await session.exec(
            select(GeneratedDocument)
            .where(
                GeneratedDocument.application_id == application_id,
                GeneratedDocument.kind == kind,
                GeneratedDocument.error.is_(None),
            )
            .order_by(GeneratedDocument.compiled_at.desc())
            .limit(1)
        )
    ).one_or_none()


async def recompile_resume_from_selection(
    session: AsyncSession,
    application: Application,
    *,
    settings: Settings,
) -> GeneratedDocument | None:
    """Recompile the resume PDF from the latest doc's selection + per-app
    overrides (text edits, include/exclude toggles). No LLM calls.

    Returns the updated GeneratedDocument, or None when nothing has been
    generated yet. May legitimately produce >1 page when the user forces
    extra bullets in — the caller surfaces the page count honestly.
    """
    doc = await svc()._latest_error_free_doc(session, application.id, GeneratedDocumentKind.RESUME)
    if doc is None or not doc.bullet_selection:
        return None
    snap = await svc().load_profile_snapshot(session, application.user_id)
    if snap is None:
        return None
    blob = dict(doc.bullet_selection)
    selected_ids = [int(b) for b in (blob.get("selected_ids") or [])]
    trimmed = {int(k): str(v) for k, v in (blob.get("trimmed_lines") or {}).items()}

    include_overrides = _application_bullet_overrides(application)
    text_overrides = _application_text_overrides(application)
    live_ids = {b.id for b in _bullet_inventory(snap)}

    effective = [
        bid
        for bid in selected_ids
        if bid in live_ids
        and include_overrides.get(bid) != BulletSelectionOverride.NEVER_INCLUDE.value
    ]
    forced_in = [
        bid
        for bid, ov in include_overrides.items()
        if ov == BulletSelectionOverride.ALWAYS_INCLUDE.value
        and bid in live_ids
        and bid not in effective
    ]
    effective.extend(sorted(forced_in))

    if not effective:
        # No live tailored line survives — the profile was re-extracted since
        # generation (all selected ids orphaned) or every bullet is excluded.
        # Compiling an empty-experience resume and calling it "updated" would
        # be a lie; the caller surfaces the regenerate affordance instead.
        log.warning(
            "recompile for application %d has no usable selection (stale doc?)", application.id
        )
        return None

    by_id = {b.id: b for b in _bullet_inventory(snap)}
    texts: dict[int, str] = {}
    for bid in effective:
        texts[bid] = text_overrides.get(bid) or trimmed.get(bid) or by_id[bid].text

    # Honor the generation pass's space-driven section drops so a selection
    # recompile reproduces the same page (never_include rows are filtered by
    # the payload builder from the live model state either way).
    excluded_projects: set[int] = set()
    excluded_certs: set[int] = set()
    for entry in blob.get("dropped_sections") or []:
        if not isinstance(entry, dict):
            continue
        kind_, sid = entry.get("kind"), entry.get("id")
        if not isinstance(sid, int):
            continue
        (excluded_projects if kind_ == "project" else excluded_certs).add(sid)

    template_name, pdf_standard = _select_template(application, settings)
    out_pdf = svc()._app_documents_dir(application.id) / "resume.pdf"
    data = await _build_resume_data(
        snap=snap,
        selected_bullet_ids=effective,
        trimmed=texts,
        tailored_summary=(blob.get("summary") or None),
        excluded_project_ids=excluded_projects,
        excluded_certification_ids=excluded_certs,
    )
    result = await svc().typst_compile(template_name, data, out_pdf, pdf_standard=pdf_standard)

    blob["selected_ids"] = effective
    blob["trimmed_lines"] = {str(k): v for k, v in texts.items()}
    blob["edited_in_workspace"] = True
    doc.bullet_selection = blob
    doc.byte_size = result.byte_size
    doc.page_count = result.page_count
    doc.compiled_at = result.compiled_at
    session.add(doc)
    await session.flush()
    return doc


async def recompile_cover_letter_from_sections(
    session: AsyncSession,
    application: Application,
    *,
    settings: Settings,
) -> GeneratedDocument | None:
    """Recompile the cover-letter PDF from the latest doc's (edited)
    `sections` blob so the embed matches what the user saved. No LLM calls.
    """
    doc = await svc()._latest_error_free_doc(
        session, application.id, GeneratedDocumentKind.COVER_LETTER
    )
    if doc is None or not doc.bullet_selection:
        return None
    sections = doc.bullet_selection.get("sections")
    if not isinstance(sections, dict):
        return None
    snap = await svc().load_profile_snapshot(session, application.user_id)
    if snap is None:
        return None
    job = None
    if application.job_id is not None:
        job = (await session.exec(select(Job).where(Job.id == application.job_id))).one_or_none()
    if job is None:
        return None

    hm_used = doc.bullet_selection.get("hiring_manager_used") or {}
    recipient_name = str(hm_used.get("name")) if hm_used.get("name") else None
    recipient_title = hm_used.get("title") if recipient_name else None
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
        "letter": {
            "intro": str(sections.get("intro", "")),
            "body": str(sections.get("body", "")),
            "why_company": str(sections.get("why_company", "")),
            "close": str(sections.get("close", "")),
        },
        "today": datetime.now(UTC).strftime("%B %-d, %Y"),
    }
    out_pdf = svc()._app_documents_dir(application.id) / "cover-letter.pdf"
    result = await svc().typst_compile("cover_letter", typst_data, out_pdf)
    doc.byte_size = result.byte_size
    doc.page_count = result.page_count
    doc.compiled_at = result.compiled_at
    session.add(doc)
    await session.flush()
    return doc


@dataclass(slots=True)
class PreGenerateResult:
    skipped_reason: str | None = None
    resume: GeneratedDocument | None = None
    cover_letter: GeneratedDocument | None = None
    screeners: list[ApplicationScreenerAnswer] | None = None


async def pre_generate(
    session: AsyncSession,
    application: Application,
    *,
    settings: Settings,
    job: Job | None = None,
    force: bool = False,
) -> PreGenerateResult:
    """Run resume + cover letter + screener generation for an Application.

    Honors:
    - **DRAFT reuse heuristic** (plan 10 § C.2): no-op when docs are READY,
      bullets unedited since compile, and JD hash unchanged.
    - **Cost cap** (plan 10 § C.2): aborts before any LLM call when today's
      `ApiUsage.cost_usd` sum exceeds `Settings.daily_llm_cost_cap_usd`.

    `force=True` bypasses both gates (used by manual "Regenerate" actions).
    """
    if job is None and application.job_id is not None:
        job = (await session.exec(select(Job).where(Job.id == application.job_id))).one_or_none()

    if not force:
        if await svc().is_cost_capped(session, application.user_id, settings):
            return PreGenerateResult(skipped_reason="cost_cap_reached")
        if await svc().can_reuse_existing_resume(session, application, job):
            return PreGenerateResult(skipped_reason="reuse_heuristic")

    resume = await svc().generate_resume(session, application, settings=settings, job=job)
    cover = await svc().generate_cover_letter(session, application, settings=settings, job=job)
    screeners = await svc().answer_screeners(session, application, settings=settings, job=job)
    return PreGenerateResult(resume=resume, cover_letter=cover, screeners=screeners)


async def cleanup_stale(session: AsyncSession, *, older_than_days: int = 30) -> int:
    """Sweep GeneratedDocument rows older than N days that point at a missing
    PDF on disk. Returns count of rows pruned. Wired to weekly cron.
    """
    threshold = datetime.now(UTC).timestamp() - older_than_days * 86400
    docs = (
        await session.exec(
            select(GeneratedDocument).where(
                GeneratedDocument.compiled_at < datetime.fromtimestamp(threshold, UTC)
            )
        )
    ).all()
    pruned = 0
    for doc in docs:
        path = Path(doc.path)
        if not path.exists():
            await session.delete(doc)
            pruned += 1
    await session.flush()
    return pruned
