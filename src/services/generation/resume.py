"""Tailored 1-page resume generation — data build, template select, page-fit loop, density add-back; plus the generic (no-JD) resume.

Split out of the former services/document_generator.py in plan 91 Phase 4.3;
behaviour unchanged. Internal calls to patched seams go through `svc()`
(the facade) so test interception keeps working.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import (
    Application,
    Bullet,
    DocsState,
    GeneratedDocument,
    GeneratedDocumentKind,
    Job,
    Profile,
    Project,
    Settings,
)
from models.enums import BulletSelectionOverride
from services.generation.bullet_selection import (
    _ai_rank_bullets,
    _refine_one_bullet,
    _split_bullets_by_override,
    _tailor_summary,
)
from services.generation.common import _select_template, _template_version, svc
from services.generation.cost_cap import CostCapExceededError
from services.generation.snapshot import (
    ProfileSnapshot,
    _bullet_inventory,
    _hash_jd,
)
from typst import overflows
from typst.compiler import TypstError

log = logging.getLogger(__name__)


log = logging.getLogger(__name__)


def _format_date(d: datetime | None) -> str | None:
    if d is None:
        return None
    return d.strftime("%b %Y")


def _strip_scheme(url: str) -> str:
    return url.removeprefix("https://").removeprefix("http://").rstrip("/")


def _normalize_handle(handle: str, domain_prefix: str) -> str:
    """Accept either a bare handle or a pasted profile URL."""
    h = _strip_scheme(handle.strip()).removeprefix("www.")
    if h.startswith(domain_prefix):
        h = h[len(domain_prefix) :]
    return h.strip("/")


def _contact_lines(p: Profile) -> list[list[dict[str, str | None]]]:
    """Two centered header lines, mirroring cv.tex's \\contactinfo pair:
    phone | email | location, then portfolio | github | linkedin. Empty
    fields are simply absent; an entirely empty line is dropped."""
    line1: list[dict[str, str | None]] = []
    if p.phone:
        line1.append({"text": p.phone, "href": None})
    if p.email:
        line1.append({"text": p.email, "href": f"mailto:{p.email}"})
    if p.location:
        line1.append({"text": p.location, "href": None})
    line2: list[dict[str, str | None]] = []
    if getattr(p, "portfolio_url", None):
        display = _strip_scheme(p.portfolio_url)
        line2.append({"text": display, "href": f"https://{display}"})
    if getattr(p, "github_handle", None):
        handle = _normalize_handle(p.github_handle, "github.com/")
        line2.append({"text": f"github.com/{handle}", "href": f"https://github.com/{handle}"})
    if getattr(p, "linkedin_handle", None):
        handle = _normalize_handle(p.linkedin_handle, "linkedin.com/in/")
        line2.append(
            {"text": f"linkedin.com/in/{handle}", "href": f"https://linkedin.com/in/{handle}"}
        )
    return [line for line in (line1, line2) if line]


def _date_range(start, end) -> str:
    start_s = _format_date(start) or ""
    end_s = _format_date(end) or "Present"
    return f"{start_s} – {end_s}" if start_s else end_s


def _section_included(row: Any, excluded: set[int]) -> bool:
    """Three-state include for Project/Certification rows: `never_include`
    never renders, `always_include` always renders, null renders unless the
    page-fit loop excluded it for space."""
    override = getattr(row, "selection_override", None)
    value = getattr(override, "value", override)
    if value == BulletSelectionOverride.NEVER_INCLUDE.value:
        return False
    if value == BulletSelectionOverride.ALWAYS_INCLUDE.value:
        return True
    return getattr(row, "id", None) not in excluded


async def _build_resume_data(
    *,
    snap: ProfileSnapshot,
    selected_bullet_ids: list[int],
    trimmed: dict[int, str],
    tailored_summary: str | None = None,
    excluded_project_ids: set[int] | None = None,
    excluded_certification_ids: set[int] | None = None,
) -> dict[str, Any]:
    """Compose the payload consumed by `onepage.typ` (cv.tex-conversion shape).

    Every experience renders — an experience may carry fewer bullets after
    the page-fit loop, but it never silently vanishes (the old
    `if not kept: continue` ate whole jobs when the selection cap starved
    them). Kept bullets are ordered by selection priority (bold tailoring:
    the most JD-relevant result leads each role).

    There is deliberately no headline field — the header is name + two
    contact lines, nothing else (cv.tex shape).
    """
    excluded_projects = excluded_project_ids or set()
    excluded_certs = excluded_certification_ids or set()
    selected = set(selected_bullet_ids)
    priority = {bid: i for i, bid in enumerate(selected_bullet_ids)}
    experiences_payload: list[dict] = []
    for exp in snap.experiences:
        bullets = snap.bullets_by_experience.get(exp.id, [])
        kept = [b for b in bullets if b.id in selected]
        kept.sort(key=lambda b: priority.get(b.id, 10_000))
        company = exp.company
        if exp.team:
            company = f"{exp.company}, {exp.team}"
        experiences_payload.append(
            {
                "company": company,
                "title": exp.title,
                "location": exp.location or "",
                "dates": _date_range(exp.start_date, exp.end_date),
                "bullets": [trimmed.get(b.id, b.text) for b in kept],
            }
        )
    p = snap.profile
    # `summary_full` is the user-editable master (item 1); `summary_short`
    # is the AI-condensed leftover kept only as a fallback.
    summary = tailored_summary or p.summary_short or p.summary_full or None
    education_payload = [
        {
            "institution": e.institution,
            "school": e.school,
            "location": e.location or "",
            "dates": _date_range(e.start_date, e.end_date),
            "degree": e.degree,
            "gpa": e.gpa,
        }
        for e in snap.education
    ]

    def _project_payload(rows: list[Project]) -> list[dict]:
        out = []
        for pr in rows:
            if not _section_included(pr, excluded_projects):
                continue
            link = getattr(pr, "link", None)
            out.append(
                {
                    "title": pr.title,
                    "date": _format_date(getattr(pr, "date", None)),
                    "text": (pr.text or None),
                    "link": (f"https://{_strip_scheme(link)}" if link else None),
                }
            )
        return out

    certifications_payload = [
        {
            "title": f"{c.title} - {c.issuer}" if c.issuer else c.title,
            "date": _format_date(getattr(c, "date", None)),
            "text": (c.description or None),
        }
        for c in snap.certifications
        if _section_included(c, excluded_certs)
    ]
    return {
        "profile": {"full_name": p.full_name},
        "contact_lines": _contact_lines(p),
        "summary": summary if summary else None,
        "experiences": experiences_payload,
        "education": education_payload,
        "skills": [{"category": s.category, "items": list(s.items)} for s in snap.skills],
        "projects": _project_payload(snap.projects),
        "open_source": _project_payload(snap.open_source),
        "certifications": certifications_payload,
    }


def _application_bullet_overrides(application: Application) -> dict[int, str]:
    """Extract per-app bullet overrides from `submission_artifacts` (plan 86 / 0.4.5.08).

    Returns `{bullet_id: "always_include" | "never_include"}`. The wire shape
    keys by `str(bid)` (JSONB friendly); this normalizes to `int` for the
    document generator's resolver. Silently drops malformed entries.
    """
    artifacts = getattr(application, "submission_artifacts", None) or {}
    raw = artifacts.get("bullet_overrides") if isinstance(artifacts, dict) else None
    if not isinstance(raw, dict):
        return {}
    out: dict[int, str] = {}
    for key, value in raw.items():
        if not isinstance(value, str):
            continue
        if value not in (
            BulletSelectionOverride.ALWAYS_INCLUDE.value,
            BulletSelectionOverride.NEVER_INCLUDE.value,
        ):
            continue
        try:
            out[int(key)] = value
        except (TypeError, ValueError):
            continue
    return out


# Start the page-fit loop with this many bullets; the loop drops from the
# tail until the page fits, which packs the page as densely as it will go.
RESUME_MAX_START_BULLETS = 22
# Density add-back cap — bounds LLM refine calls + typst compiles after the
# fit loop when spare page room remains.
RESUME_MAX_ADDBACK = 8


def _ensure_min_one_per_experience(
    candidate_ids: list[int], ranked_ids: list[int], snap: ProfileSnapshot
) -> list[int]:
    """Every experience contributes at least one bullet to the candidate set.

    The old top-N cut starved older experiences to zero bullets and the
    renderer then dropped the whole job. Missing experiences get their
    highest-ranked bullet appended.
    """
    candidate = set(candidate_ids)
    rank = {bid: i for i, bid in enumerate(ranked_ids)}
    out = list(candidate_ids)
    for exp in snap.experiences:
        bullets = snap.bullets_by_experience.get(exp.id, [])
        if not bullets or any(b.id in candidate for b in bullets):
            continue
        ranked_for_exp = [b.id for b in bullets if b.id in rank]
        if not ranked_for_exp:
            continue
        best = min(ranked_for_exp, key=lambda bid: rank[bid])
        out.append(best)
        candidate.add(best)
    return out


def _drop_lowest_priority(
    candidate_ids: list[int], snap: ProfileSnapshot, *, allow_floor_drop: bool = True
) -> tuple[list[int], int | None]:
    """Drop the lowest-priority bullet whose experience keeps ≥1 bullet.

    With `allow_floor_drop` it falls back to a plain tail-drop when every
    experience is down to its last bullet (the page has to fit eventually).
    Callers pass False while cheaper space remains elsewhere (null-override
    Projects / Certifications / Open-Source rows drop before an experience
    is emptied).
    """
    exp_of = {b.id: exp_id for exp_id, bs in snap.bullets_by_experience.items() for b in bs}
    counts: dict[int, int] = {}
    for bid in candidate_ids:
        eid = exp_of.get(bid)
        if eid is not None:
            counts[eid] = counts.get(eid, 0) + 1
    for i in range(len(candidate_ids) - 1, -1, -1):
        bid = candidate_ids[i]
        eid = exp_of.get(bid)
        if eid is None or counts.get(eid, 0) > 1:
            return candidate_ids[:i] + candidate_ids[i + 1 :], bid
    if allow_floor_drop and candidate_ids:
        return candidate_ids[:-1], candidate_ids[-1]
    return candidate_ids, None


def _section_drop_queue(snap: ProfileSnapshot) -> list[tuple[str, int]]:
    """Null-override section rows in drop order (least prominent first):
    Open Source tail→head, then Certifications, then Projects. Rows pinned
    `always_include` never enter the queue; `never_include` rows are already
    filtered out of the payload."""
    queue: list[tuple[str, int]] = []
    for pr in reversed(snap.open_source):
        if getattr(pr, "selection_override", None) is None and pr.id is not None:
            queue.append(("project", pr.id))
    for cert in reversed(snap.certifications):
        if getattr(cert, "selection_override", None) is None and cert.id is not None:
            queue.append(("certification", cert.id))
    for pr in reversed(snap.projects):
        if getattr(pr, "selection_override", None) is None and pr.id is not None:
            queue.append(("project", pr.id))
    return queue


async def generate_resume(
    session: AsyncSession,
    application: Application,
    *,
    settings: Settings,
    job: Job | None = None,
    system: str | None = None,
    cache_system: bool = False,
) -> GeneratedDocument:
    """Generate a tailored 1-page resume for `application`.

    Bold-tailoring contract:
    - The LLM ranks the FULL bullet inventory against the JD; the page-fit
      loop starts generous (`RESUME_MAX_START_BULLETS`) and drops the
      lowest-priority bullet on overflow.
    - After the page fits, the ADD-BACK pass pulls the next-ranked bullets
      in (even sub-relevant ones) until adding one more would overflow —
      the page ends up PACKED, not just "under the limit". Selected
      JD-relevant content still leads each role.
    - Every selected bullet is REWRITTEN against the JD (`refine_bullet`):
      mirror the posting's terminology where truthful, one printed line.
    - Every experience keeps ≥1 bullet; no job ever silently vanishes.
    - The summary is rewritten per-JD (`tailor_summary`).

    Raises `CostCapExceededError` when today's spend exceeded the user's cap.
    `system` + `cache_system` thread the voice-grounded constitution preamble
    (plan 66 § T2) into every LLM call within the resume pipeline.
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

    application.docs_state = DocsState.GENERATING
    session.add(application)
    await session.flush()

    application_overrides = _application_bullet_overrides(application)
    ranked_ids = await _ai_rank_bullets(
        session=session,
        settings=settings,
        snap=snap,
        job=job,
        user_id=user_id,
        application_id=application.id,
        system=system,
        cache_system=cache_system,
        application_overrides=application_overrides or None,
    )
    candidate_ids = _ensure_min_one_per_experience(
        ranked_ids[:RESUME_MAX_START_BULLETS], ranked_ids, snap
    )

    job_text = job.description or job.description_html or ""
    candidate_set = set(candidate_ids)
    selected_bullets: list[Bullet] = [b for b in _bullet_inventory(snap) if b.id in candidate_set]
    trimmed: dict[int, str] = {}
    for b in selected_bullets:
        trimmed[b.id] = await _refine_one_bullet(
            session=session,
            settings=settings,
            user_id=user_id,
            application_id=application.id,
            bullet=b,
            job_text=job_text,
            system=system,
            cache_system=cache_system,
        )

    tailored_summary = await _tailor_summary(
        session=session,
        settings=settings,
        snap=snap,
        job=job,
        user_id=user_id,
        application_id=application.id,
        ranked_bullet_ids=ranked_ids,
        system=system,
        cache_system=cache_system,
    )

    out_dir = svc()._app_documents_dir(application.id)
    out_pdf = out_dir / "resume.pdf"

    template_name, pdf_standard = _select_template(application, settings)

    # Page-fit loop: pack the page, dropping the lowest-priority bullet on
    # overflow — never emptying an experience. When bullets hit the
    # one-per-experience floor, null-override section rows (OSS → certs →
    # projects) become the remaining space to reclaim.
    dropped_for_fit: list[int] = []
    section_queue = _section_drop_queue(snap)
    dropped_sections: list[dict[str, Any]] = []
    excluded_projects: set[int] = set()
    excluded_certs: set[int] = set()
    final_result = None
    result = None
    # Budget = the droppable inventory itself: every failing attempt removes
    # one bullet or one section row, so the loop exits on "fits" or "nothing
    # left to drop" — never by running out of attempts with droppable content
    # remaining (the old fixed cap shipped silent 2-pagers that way).
    max_fit_attempts = len(candidate_ids) + len(section_queue) + 1
    for _attempt in range(max_fit_attempts):
        data = await _build_resume_data(
            snap=snap,
            selected_bullet_ids=candidate_ids,
            trimmed=trimmed,
            tailored_summary=tailored_summary,
            excluded_project_ids=excluded_projects,
            excluded_certification_ids=excluded_certs,
        )
        try:
            result = await svc().typst_compile(
                template_name, data, out_pdf, pdf_standard=pdf_standard
            )
        except TypstError as exc:
            application.docs_state = DocsState.FAILED
            session.add(application)
            doc = GeneratedDocument(
                application_id=application.id,
                kind=GeneratedDocumentKind.RESUME,
                path=str(out_pdf),
                byte_size=0,
                page_count=None,
                compiled_at=datetime.now(UTC),
                model=settings.llm_model,
                error=str(exc),
                bullet_selection={
                    "selected_ids": candidate_ids,
                    "trimmed_lines": {str(k): v for k, v in trimmed.items()},
                    "jd_hash": _hash_jd(job.description_html or job.description),
                },
            )
            session.add(doc)
            await session.flush()
            return doc
        if not overflows(result, max_pages=1):
            final_result = result
            break
        candidate_ids, dropped = _drop_lowest_priority(
            candidate_ids, snap, allow_floor_drop=not section_queue
        )
        if dropped is not None:
            dropped_for_fit.append(dropped)
            log.info("resume overflowed page 1; dropped bullet %d (fit loop)", dropped)
            continue
        if section_queue:
            kind_, sid = section_queue.pop(0)
            (excluded_projects if kind_ == "project" else excluded_certs).add(sid)
            dropped_sections.append({"kind": kind_, "id": sid})
            log.info("resume overflowed page 1; dropped %s %d (fit loop)", kind_, sid)
            continue
        final_result = result
        break
    else:  # pragma: no cover — budget spans the whole droppable inventory
        final_result = result

    overflow_accepted = final_result is not None and overflows(final_result, max_pages=1)
    if overflow_accepted:
        log.warning(
            "resume for application %d still overflows (%s pages) after exhausting "
            "every droppable bullet and section — accepting, flagged in bullet_selection",
            application.id,
            final_result.page_count,
        )

    # Density add-back pass: the fit loop stops at "fits"; a packed page
    # wants the NEXT-ranked bullets back in even when they're only
    # sub-relevant to this JD. Add one at a time in rank order until adding
    # one more would overflow, then rewind that last add. Bullets dropped BY
    # the fit loop stay dropped (they already proved they don't fit).
    added_back: list[int] = []
    if final_result is not None and not overflows(final_result, max_pages=1):
        skip = set(candidate_ids) | set(dropped_for_fit)
        addback_queue = [bid for bid in ranked_ids if bid not in skip]
        by_id = {b.id: b for b in _bullet_inventory(snap)}
        disk_pdf_overflows = False
        for bid in addback_queue[:RESUME_MAX_ADDBACK]:
            bullet = by_id.get(bid)
            if bullet is None:
                continue
            if bid not in trimmed:
                trimmed[bid] = await _refine_one_bullet(
                    session=session,
                    settings=settings,
                    user_id=user_id,
                    application_id=application.id,
                    bullet=bullet,
                    job_text=job_text,
                    system=system,
                    cache_system=cache_system,
                )
            attempt_ids = [*candidate_ids, bid]
            data = await _build_resume_data(
                snap=snap,
                selected_bullet_ids=attempt_ids,
                trimmed=trimmed,
                tailored_summary=tailored_summary,
                excluded_project_ids=excluded_projects,
                excluded_certification_ids=excluded_certs,
            )
            try:
                result = await svc().typst_compile(
                    template_name, data, out_pdf, pdf_standard=pdf_standard
                )
            except TypstError as exc:
                log.warning("add-back compile failed; keeping fitted page: %s", exc)
                disk_pdf_overflows = True  # disk state unknown — recompile below
                break
            if overflows(result, max_pages=1):
                disk_pdf_overflows = True
                break
            candidate_ids = attempt_ids
            added_back.append(bid)
            final_result = result
        if disk_pdf_overflows:
            # The last attempted add overflowed (or failed) — the PDF on
            # disk is not the fitted selection; recompile it.
            data = await _build_resume_data(
                snap=snap,
                selected_bullet_ids=candidate_ids,
                trimmed=trimmed,
                tailored_summary=tailored_summary,
                excluded_project_ids=excluded_projects,
                excluded_certification_ids=excluded_certs,
            )
            try:
                final_result = await svc().typst_compile(
                    template_name, data, out_pdf, pdf_standard=pdf_standard
                )
            except TypstError as exc:  # pragma: no cover — compiled moments ago
                log.warning("post-add-back recompile failed: %s", exc)
        if added_back:
            log.info("density add-back kept %d extra bullets", len(added_back))

    application.docs_state = DocsState.READY
    session.add(application)

    selection_blob: dict[str, Any] = {
        "selected_ids": candidate_ids,
        "ranked_ids": ranked_ids,
        "dropped_for_fit": dropped_for_fit,
        "dropped_sections": dropped_sections,
        "added_back": added_back,
        "summary": tailored_summary,
        "trimmed_lines": {str(k): v for k, v in trimmed.items()},
        "jd_hash": _hash_jd(job.description_html or job.description),
        "template_version": _template_version(template_name),
    }
    if overflow_accepted:
        selection_blob["overflow_accepted"] = True

    doc = GeneratedDocument(
        application_id=application.id,
        kind=GeneratedDocumentKind.RESUME,
        path=str(out_pdf),
        byte_size=final_result.byte_size,
        page_count=final_result.page_count,
        compiled_at=final_result.compiled_at,
        model=settings.llm_model,
        bullet_selection=selection_blob,
    )
    session.add(doc)
    await session.flush()
    return doc


# ── Generic resume (no JD; for portfolio sync) ─────────────────────────


async def generate_generic_resume(
    session: AsyncSession,
    *,
    user_id: int,
    settings: Settings,
    output_path: Path,
) -> GeneratedDocument | None:
    """Generate a Profile-only resume (no JD context); used by portfolio_sync.

    No `Application` row — the document is not persisted to the
    GeneratedDocument table (returns None on success). The PDF lives at
    `output_path` (typically `~/.naavik/data/documents/portfolio/resume.pdf`).
    Bullet selection: ALWAYS_INCLUDE first, then by tag count.
    """
    snap = await svc().load_profile_snapshot(session, user_id)
    if snap is None:
        return None
    inventory = _bullet_inventory(snap)
    always, never, auto = _split_bullets_by_override(inventory)
    auto_sorted = sorted(auto, key=lambda b: -len(b.tags or []))
    selected = [*always, *auto_sorted[: max(0, 12 - len(always))]]
    selected_ids = [b.id for b in selected]
    trimmed: dict[int, str] = {}
    for b in selected:
        # No LLM trim — just truncate, keeping the cost low.
        trimmed[b.id] = b.text if len(b.text) <= 140 else b.text[:139] + "…"
    data = await _build_resume_data(
        snap=snap,
        selected_bullet_ids=selected_ids,
        trimmed=trimmed,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Same 1-page contract as the tailored path, LLM-free: drop the
    # lowest-priority bullet (sections reclaim space once bullets hit the
    # one-per-experience floor) and recompile until the page fits.
    section_queue = _section_drop_queue(snap)
    excluded_projects: set[int] = set()
    excluded_certs: set[int] = set()
    try:
        result = await svc().typst_compile("onepage", data, output_path)
        while overflows(result, max_pages=1):
            selected_ids, dropped = _drop_lowest_priority(
                selected_ids, snap, allow_floor_drop=not section_queue
            )
            if dropped is None:
                if not section_queue:
                    log.warning(
                        "generic resume still overflows (%s pages) with nothing left to drop",
                        result.page_count,
                    )
                    break
                kind_, sid = section_queue.pop(0)
                (excluded_projects if kind_ == "project" else excluded_certs).add(sid)
            data = await _build_resume_data(
                snap=snap,
                selected_bullet_ids=selected_ids,
                trimmed=trimmed,
                excluded_project_ids=excluded_projects,
                excluded_certification_ids=excluded_certs,
            )
            result = await svc().typst_compile("onepage", data, output_path)
    except TypstError:
        return None
    return GeneratedDocument(
        application_id=0,  # synthetic — not persisted
        kind=GeneratedDocumentKind.RESUME,
        path=str(output_path),
        byte_size=result.byte_size,
        page_count=result.page_count,
        compiled_at=result.compiled_at,
        model=settings.llm_model,
    )
