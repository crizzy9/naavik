"""Document generator — resume + cover letter + screener-answer pipeline.

Per BACKEND.md § K.4 + plan 10 § C.2 + DATA_MODEL.md § J.

The four entry points:

- `generate_resume(application)`     — bullet selection + AI trim + Typst → PDF
- `generate_cover_letter(application)` — 4-section letter via LLM + Typst → PDF
- `answer_screeners(application)`    — auto-fill from Profile + AI-draft the rest
- `pre_generate(application)`        — runs all three, gated on Settings

Cost / DRAFT-reuse semantics live here:

- **Reuse heuristic.** `pre_generate` is a no-op if `docs_state == READY` AND
  every selected bullet has `edited_at <= GeneratedDocument.compiled_at` AND
  the JD hash recorded on the latest resume matches the current Job.
- **Cost cap.** When `Settings.daily_llm_cost_cap_usd` is set and today's
  `sum(ApiUsage.cost_usd)` ≥ cap, generation is aborted; the route handler
  surfaces the lazy CTA + a "cost cap reached" banner.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from config import settings as app_settings
from llm import LLMProvider, LLMProviderError, get_provider
from models import (
    ApiUsage,
    Application,
    ApplicationScreenerAnswer,
    Bullet,
    DocsState,
    Education,
    Experience,
    GeneratedDocument,
    GeneratedDocumentKind,
    Job,
    Profile,
    Project,
    ScreenerAnswerSource,
    ScreenerQuestionType,
    Settings,
    Skill,
)
from models.enums import ApplicationBoard, BulletSelectionOverride
from services import llm_tracker
from typst import compile as typst_compile
from typst import overflows
from typst.compiler import TypstError

# Plan 66 (0.3.1) § T6 — auto-select the ATS-friendly template variant for
# ATS-known boards; manual + company-direct stays on creative onepage.typ.
# ApplicationBoard enum only carries the ATS surfaces we have adapters for;
# additional boards (ICIMS / TALEO / SAP_SUCCESSFACTORS / BAMBOOHR / JAZZHR)
# from the research memo's ATS allowlist are deferred until those adapters
# ship per ROADMAP.
_ATS_BOARDS: frozenset[ApplicationBoard] = frozenset(
    {
        ApplicationBoard.WORKDAY,
        ApplicationBoard.GREENHOUSE,
        ApplicationBoard.LEVER,
        ApplicationBoard.ASHBY,
        ApplicationBoard.LINKEDIN,
    }
)

log = logging.getLogger(__name__)


# Documents directory — relative to DATA_DIR; per-app subdir.
def _documents_dir() -> Path:
    raw = app_settings.data_dir
    base = Path(raw).expanduser() if raw.startswith("~") else Path(raw)
    if not base.is_absolute():
        base = base.resolve()
    return base / "data" / "documents"


def _app_documents_dir(application_id: int) -> Path:
    d = _documents_dir() / str(application_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── Cost cap helpers ────────────────────────────────────────────────────


class CostCapExceededError(Exception):
    """Today's LLM spend exceeded `Settings.daily_llm_cost_cap_usd`."""


async def _today_spend(session: AsyncSession, user_id: int) -> float:
    """Sum `ApiUsage.cost_usd` for the current UTC day for one user."""
    today_start = datetime.combine(date.today(), datetime.min.time(), tzinfo=UTC)
    stmt = select(func.coalesce(func.sum(ApiUsage.cost_usd), 0.0)).where(
        ApiUsage.user_id == user_id,
        ApiUsage.occurred_at >= today_start,
        ApiUsage.succeeded.is_(True),
    )
    result = (await session.exec(stmt)).one()
    if isinstance(result, tuple):
        result = result[0]
    return float(result or 0.0)


async def is_cost_capped(session: AsyncSession, user_id: int, settings: Settings) -> bool:
    """Return True if `daily_llm_cost_cap_usd` is set and reached."""
    if settings.daily_llm_cost_cap_usd is None:
        return False
    spent = await _today_spend(session, user_id)
    return spent >= float(settings.daily_llm_cost_cap_usd)


# ── Reuse-heuristic helpers ─────────────────────────────────────────────


def _hash_jd(text: str | None) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:32]


async def _latest_resume(session: AsyncSession, application_id: int) -> GeneratedDocument | None:
    stmt = (
        select(GeneratedDocument)
        .where(
            GeneratedDocument.application_id == application_id,
            GeneratedDocument.kind == GeneratedDocumentKind.RESUME,
            GeneratedDocument.error.is_(None),
        )
        .order_by(GeneratedDocument.compiled_at.desc())
        .limit(1)
    )
    return (await session.exec(stmt)).one_or_none()


async def can_reuse_existing_resume(
    session: AsyncSession, application: Application, job: Job | None
) -> bool:
    """DRAFT reuse heuristic per plan 10 § C.2.

    Returns True iff:
      1. application.docs_state == READY
      2. for every selected bullet_id, Bullet.edited_at <= GeneratedDocument.compiled_at
      3. job.description_html hash matches the JD hash on the latest resume row
    """
    if application.docs_state != DocsState.READY:
        return False
    latest = await _latest_resume(session, application.id)
    if latest is None or not latest.bullet_selection:
        return False
    selected_ids = latest.bullet_selection.get("selected_ids") or []
    if not selected_ids:
        return False
    # Compare bullet edits
    stmt = select(Bullet).where(Bullet.id.in_(selected_ids))
    bullets = (await session.exec(stmt)).all()
    for b in bullets:
        if b.edited_at and b.edited_at > latest.compiled_at:
            return False
    # Compare JD hash
    cur_hash = _hash_jd((job.description_html or job.description) if job else "")
    stored_hash = (latest.bullet_selection or {}).get("jd_hash", "")
    return cur_hash == stored_hash


# ── Profile loaders ─────────────────────────────────────────────────────


@dataclass(slots=True)
class ProfileSnapshot:
    profile: Profile
    experiences: list[Experience]
    bullets_by_experience: dict[int, list[Bullet]]
    skills: list[Skill]
    education: list[Education]
    projects: list[Project]


async def load_profile_snapshot(session: AsyncSession, user_id: int) -> ProfileSnapshot | None:
    profile = (
        await session.exec(
            select(Profile).where(Profile.user_id == user_id, Profile.deleted_at.is_(None))
        )
    ).one_or_none()
    if profile is None:
        return None
    experiences = (
        await session.exec(
            select(Experience)
            .where(Experience.profile_id == profile.id, Experience.deleted_at.is_(None))
            .order_by(Experience.order_index)
        )
    ).all()
    bullets_by_exp: dict[int, list[Bullet]] = {}
    for exp in experiences:
        bullets = (
            await session.exec(
                select(Bullet)
                .where(Bullet.experience_id == exp.id, Bullet.deleted_at.is_(None))
                .order_by(Bullet.order_index)
            )
        ).all()
        bullets_by_exp[exp.id] = bullets
    skills = (
        await session.exec(
            select(Skill).where(Skill.profile_id == profile.id).order_by(Skill.order_index)
        )
    ).all()
    education = (
        await session.exec(
            select(Education)
            .where(Education.profile_id == profile.id)
            .order_by(Education.order_index)
        )
    ).all()
    projects = (
        await session.exec(
            select(Project)
            .where(Project.profile_id == profile.id, Project.deleted_at.is_(None))
            .order_by(Project.order_index)
        )
    ).all()
    return ProfileSnapshot(
        profile=profile,
        experiences=experiences,
        bullets_by_experience=bullets_by_exp,
        skills=skills,
        education=education,
        projects=projects,
    )


def _bullet_inventory(snap: ProfileSnapshot) -> list[Bullet]:
    return [b for bs in snap.bullets_by_experience.values() for b in bs]


# ── Bullet selection (pre-LLM honoring overrides) ───────────────────────


def _split_bullets_by_override(
    bullets: list[Bullet],
) -> tuple[list[Bullet], list[Bullet], list[Bullet]]:
    always: list[Bullet] = []
    never: list[Bullet] = []
    auto: list[Bullet] = []
    for b in bullets:
        if b.selection_override == BulletSelectionOverride.ALWAYS_INCLUDE:
            always.append(b)
        elif b.selection_override == BulletSelectionOverride.NEVER_INCLUDE:
            never.append(b)
        else:
            auto.append(b)
    return always, never, auto


async def _ai_select_bullets(
    *,
    session: AsyncSession,
    settings: Settings,
    snap: ProfileSnapshot,
    job: Job,
    user_id: int,
    application_id: int | None,
    max_select: int = 12,
    system: str | None = None,
    cache_system: bool = False,
) -> list[int]:
    """Return ordered list of selected bullet ids honoring overrides + LLM."""
    inventory = _bullet_inventory(snap)
    if not inventory:
        return []
    always, never, auto = _split_bullets_by_override(inventory)

    selected_ids: list[int] = [b.id for b in always]
    remaining = max_select - len(selected_ids)
    if remaining <= 0 or not auto:
        return selected_ids[:max_select]

    # AI-pick the rest from `auto` only (skip never).
    provider = get_provider(settings)
    bullet_payload = [{"id": b.id, "text": b.text} for b in auto]
    job_payload = {
        "role": job.role,
        "description": job.description or job.description_html or "",
        "skills_required": list(job.skills_required or []),
    }
    try:
        result = await llm_tracker.tracked_call(
            session=session,
            user_id=user_id,
            provider=provider,
            method="structured",
            prompt_name="select_bullets",
            application_id=application_id,
            prompt=_render_select_prompt(bullet_payload, job_payload, remaining),
            schema=__import__(
                "llm.prompts.select_bullets", fromlist=["BulletSelection"]
            ).BulletSelection,
            system=system,
            cache_system=cache_system,
        )
        chosen = list(result.value.get("selected_ids", [])) if result else []
    except LLMProviderError as exc:
        log.warning("select_bullets LLM failed; falling back to first-N: %s", exc)
        chosen = [b.id for b in auto[:remaining]]
    # Defend against the model returning ids outside the auto pool.
    auto_ids = {b.id for b in auto}
    chosen = [cid for cid in chosen if cid in auto_ids]
    selected_ids.extend(chosen[:remaining])
    return selected_ids[:max_select]


def _render_select_prompt(bullets: list[dict], job: dict, remaining: int) -> str:
    lines = "\n".join(f"{b['id']} → {b['text']}" for b in bullets)
    return (
        f"Select the {remaining} most relevant bullets for this job.\n\n"
        f"Bullets:\n{lines}\n\n"
        f"Job role: {job['role']}\n"
        f"Description: {job['description'][:1000]}\n"
        f"Required skills: {', '.join(job.get('skills_required', []))}\n\n"
        "Return BulletSelection with selected_ids in priority order."
    )


# ── Resume generation ───────────────────────────────────────────────────


async def _trim_one_bullet(
    *,
    session: AsyncSession,
    settings: Settings,
    user_id: int,
    application_id: int | None,
    bullet: Bullet,
    target_chars: int = 120,
    system: str | None = None,
    cache_system: bool = False,
) -> str:
    if len(bullet.text) <= target_chars:
        return bullet.text
    provider = get_provider(settings)
    prompt = (
        f"Trim this bullet to one resume line of at most {target_chars} characters.\n\n"
        f"Original:\n{bullet.text}\n\n"
        "Preserve every number, every verb, the most concrete result. Return "
        "TrimmedBullet with trimmed + dropped_phrases."
    )
    try:
        result = await llm_tracker.tracked_call(
            session=session,
            user_id=user_id,
            provider=provider,
            method="structured",
            prompt_name="trim_bullet",
            application_id=application_id,
            prompt=prompt,
            schema=__import__("llm.prompts.trim_bullet", fromlist=["TrimmedBullet"]).TrimmedBullet,
            system=system,
            cache_system=cache_system,
        )
        return str(result.value.get("trimmed") or bullet.text)
    except LLMProviderError as exc:
        log.warning("trim_bullet failed; using truncation: %s", exc)
        return bullet.text[: target_chars - 1] + "…"


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
        provider = get_provider(settings)
        result = await llm_tracker.tracked_call(
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


async def _build_resume_data(
    *,
    snap: ProfileSnapshot,
    selected_bullet_ids: list[int],
    trimmed: dict[int, str],
    tailored_headline: str | None = None,
) -> dict[str, Any]:
    """Render the resume payload consumed by `onepage.typ` / `onepage_ats.typ`.

    `tailored_headline` (plan 66 § T7) — when present, surfaces as the
    one-line headline under the candidate's name on the ATS template;
    `onepage.typ` ignores this field.
    """
    selected = set(selected_bullet_ids)
    experiences_payload: list[dict] = []
    for exp in snap.experiences:
        bullets = snap.bullets_by_experience.get(exp.id, [])
        kept = [b for b in bullets if b.id in selected]
        if not kept:
            continue
        experiences_payload.append(
            {
                "company": exp.company,
                "role": exp.title,
                "location": exp.location,
                "start_date": _format_date(exp.start_date) or "",
                "end_date": _format_date(exp.end_date),
                "bullets": [trimmed.get(b.id, b.text) for b in kept],
            }
        )
    p = snap.profile
    return {
        "profile": {
            "full_name": p.full_name,
            "headline": p.headline,
            "email": p.email,
            "phone": p.phone,
            "location": p.location,
            "portfolio_url": p.portfolio_url,
            "linkedin_handle": p.linkedin_handle,
            "github_handle": p.github_handle,
            "summary_short": p.summary_short,
        },
        "tailored_headline": tailored_headline,
        "experiences": experiences_payload,
        "education": [
            {
                "institution": e.institution,
                "degree": e.degree,
                "start_date": _format_date(e.start_date) or "",
                "end_date": _format_date(e.end_date),
                "gpa": e.gpa,
            }
            for e in snap.education
        ],
        "skills": [{"category": s.category, "items": list(s.items)} for s in snap.skills],
        "projects": [{"title": pr.title, "text": pr.text, "link": pr.link} for pr in snap.projects],
    }


def _select_template(application: Application, settings: Settings) -> tuple[str, str | None]:
    """Pick the resume template + PDF standard for `application`.

    Plan 66 (0.3.1) § T6 + T12. Returns ``(template_name, pdf_standard)``.

    Resolution order:
    1. `Settings.resume_template_preference` ∈ {"ats", "creative"} forces the
       template explicitly.
    2. `Settings.resume_template_preference == "auto"` (default) →
       ATS variant when `Application.board` ∈ ATS-known set; creative otherwise.

    The ATS variant pairs with PDF/A-1b output (`pdf_standard="a-1b"`); the
    creative variant uses default PDF (None).
    """
    pref = getattr(settings, "resume_template_preference", "auto")
    if pref == "ats":
        return "onepage_ats", "a-1b"
    if pref == "creative":
        return "onepage", None
    # auto — board-driven
    board = getattr(application, "board", None)
    if board is not None and board in _ATS_BOARDS:
        return "onepage_ats", "a-1b"
    return "onepage", None


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

    Raises `CostCapExceededError` when today's spend exceeded the user's cap.
    On Typst overflow, drops the lowest-priority bullet and re-compiles
    (max 3 retries) before persisting `error="overflow"` and returning.

    `system` + `cache_system` thread the voice-grounded constitution preamble
    (plan 66 § T2) into every LLM call within the resume pipeline so
    Anthropic's ephemeral cache fires across stages within the bundle.
    """
    user_id = application.user_id
    if await is_cost_capped(session, user_id, settings):
        raise CostCapExceededError("daily_llm_cost_cap_usd reached")

    snap = await load_profile_snapshot(session, user_id)
    if snap is None:
        raise ValueError(f"no profile for user_id={user_id}")
    if job is None and application.job_id is not None:
        job = (await session.exec(select(Job).where(Job.id == application.job_id))).one_or_none()
    if job is None:
        raise ValueError(f"application {application.id} has no job context")

    application.docs_state = DocsState.GENERATING
    session.add(application)
    await session.flush()

    selected_ids = await _ai_select_bullets(
        session=session,
        settings=settings,
        snap=snap,
        job=job,
        user_id=user_id,
        application_id=application.id,
        max_select=12,
        system=system,
        cache_system=cache_system,
    )
    selected_bullets: list[Bullet] = [b for b in _bullet_inventory(snap) if b.id in selected_ids]
    trimmed: dict[int, str] = {}
    for b in selected_bullets:
        trimmed[b.id] = await _trim_one_bullet(
            session=session,
            settings=settings,
            user_id=user_id,
            application_id=application.id,
            bullet=b,
            target_chars=120,
            system=system,
            cache_system=cache_system,
        )

    out_dir = _app_documents_dir(application.id)
    out_pdf = out_dir / "resume.pdf"

    template_name, pdf_standard = _select_template(application, settings)

    # Page-count retry loop: drop the lowest-priority bullet on overflow.
    candidate_ids = list(selected_ids)
    final_result = None
    for attempt in range(3):
        data = await _build_resume_data(
            snap=snap,
            selected_bullet_ids=candidate_ids,
            trimmed=trimmed,
        )
        try:
            result = await typst_compile(template_name, data, out_pdf, pdf_standard=pdf_standard)
        except TypstError as exc:
            application.docs_state = DocsState.FAILED
            session.add(application)
            doc = GeneratedDocument(
                application_id=application.id,
                kind=GeneratedDocumentKind.RESUME,
                path=str(out_pdf.relative_to(_documents_dir().parent.parent)),
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
        if not candidate_ids:
            final_result = result
            break
        # Drop the last (lowest-priority) bullet and retry.
        dropped = candidate_ids.pop()
        log.info("resume overflowed page 1 (attempt %d); dropping bullet %d", attempt + 1, dropped)
    else:
        final_result = result  # noqa: F821 — set in last loop iteration

    application.docs_state = DocsState.READY
    session.add(application)

    doc = GeneratedDocument(
        application_id=application.id,
        kind=GeneratedDocumentKind.RESUME,
        path=str(out_pdf),
        byte_size=final_result.byte_size,
        page_count=final_result.page_count,
        compiled_at=final_result.compiled_at,
        model=settings.llm_model,
        bullet_selection={
            "selected_ids": candidate_ids,
            "trimmed_lines": {str(k): v for k, v in trimmed.items()},
            "jd_hash": _hash_jd(job.description_html or job.description),
        },
    )
    session.add(doc)
    await session.flush()
    return doc


# ── Cover letter ────────────────────────────────────────────────────────


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
    if await is_cost_capped(session, user_id, settings):
        raise CostCapExceededError("daily_llm_cost_cap_usd reached")

    snap = await load_profile_snapshot(session, user_id)
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

    provider = get_provider(settings)
    top_bullets = [b.text for b in _bullet_inventory(snap)[:10]]
    profile_payload = {
        "full_name": snap.profile.full_name,
        "summary_short": snap.profile.summary_short or snap.profile.summary_full or "",
        "summary_full": snap.profile.summary_full or "",
        "top_bullets": top_bullets,
    }
    job_payload = {
        "company": job.company,
        "role": job.role,
        "description": job_description,
    }
    try:
        result = await llm_tracker.tracked_call(
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
        # CoverLetterSota → cover_letter.typt payload shape (T10 mapping).
        # `hook` → intro; `match` → body; `close` → close; `why_company` empty
        # (already folded into match).
        letter_dict = {
            "intro": str(sota_value.get("hook", "")),
            "body": str(sota_value.get("match", "")),
            "why_company": "",
            "close": str(sota_value.get("close", "")),
            "_sota_format_chosen": str(sota_value.get("format_chosen", format_chosen)),
            "_sota_verbatim_phrases": list(sota_value.get("verbatim_phrases", []) or []),
            "_sota_hiring_manager_used": dict(sota_value.get("hiring_manager_used", {}) or {}),
        }
    except LLMProviderError as exc:
        log.warning("cover letter draft failed; using template: %s", exc)
        letter_dict = {
            "intro": f"I'm excited to apply for the {job.role} role at {job.company}.",
            "body": snap.profile.summary_short or "",
            "why_company": f"{job.company} is on the trajectory I want to be a part of.",
            "close": "I would love the opportunity to contribute.",
        }

    out_dir = _app_documents_dir(application.id)
    out_pdf = out_dir / "cover-letter.pdf"

    today_str = datetime.now(UTC).strftime("%B %-d, %Y")

    # Strip the SOTA-only audit fields before passing to Typst (typst template
    # only consumes {intro, body, why_company, close}).
    typst_letter = {k: v for k, v in letter_dict.items() if not k.startswith("_sota_")}

    typst_data = {
        "profile": {
            "full_name": snap.profile.full_name,
            "email": snap.profile.email,
            "phone": snap.profile.phone,
            "location": snap.profile.location,
        },
        "job": {"company": job.company, "role": job.role},
        "letter": typst_letter,
        "today": today_str,
    }
    try:
        compile_result = await typst_compile("cover_letter", typst_data, out_pdf)
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
    doc = GeneratedDocument(
        application_id=application.id,
        kind=GeneratedDocumentKind.COVER_LETTER,
        path=str(out_pdf),
        byte_size=compile_result.byte_size,
        page_count=compile_result.page_count,
        compiled_at=compile_result.compiled_at,
        model=settings.llm_model,
        bullet_selection=sota_meta if sota_meta else None,
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
    profile_str = (
        f"{profile.get('full_name', '')}\n"
        f"{profile.get('summary_short') or profile.get('summary_full', '')}\n"
        f"Top bullets: {'; '.join(top_bullets)[:1500]}"
    )
    job_str = (
        f"{job.get('company', '')} — {job.get('role', '')}\n{(job.get('description') or '')[:1500]}"
    )

    if format_chosen == "pain_letter":
        pain_signals = _PAIN_POINT_RE.findall(job.get("description", ""))[:5]
        return PROMPT_PAIN_LETTER.format(
            profile=profile_str,
            job=job_str,
            hiring_manager=hm_str,
            matched_tags=", ".join(matched_tags),
            pain_signals=", ".join(pain_signals),
        )
    return PROMPT_STANDARD.format(
        profile=profile_str,
        job=job_str,
        hiring_manager=hm_str,
        matched_tags=", ".join(matched_tags),
    )


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


# ── Screener answering ─────────────────────────────────────────────────


_AUTO_FILL_FINGERPRINTS: dict[str, str] = {
    # Lowercased keyword tokens → Profile field name.
    "earliest start": "earliest_start",
    "start date": "earliest_start",
    "salary expectation": "salary_expectation_usd",
    "salary requirement": "salary_expectation_usd",
    "work authorization": "work_authorization",
    "authorized to work": "work_authorization",
    "visa sponsorship": "visa_sponsorship_needed",
    "require sponsorship": "visa_sponsorship_needed",
    "willing to relocate": "willing_to_relocate",
    "relocate": "willing_to_relocate",
    "veteran": "veteran_status",
    "disability": "disability_status",
    "race": "race_ethnicity",
    "ethnicity": "race_ethnicity",
    "gender": "gender_identity",
}


def question_fingerprint(question_text: str) -> str:
    """Lowercase + strip punctuation + remove company name (best-effort)."""
    s = (question_text or "").lower()
    out = "".join(c if c.isalnum() or c.isspace() else " " for c in s)
    return " ".join(out.split())


def _auto_field_for_question(question_text: str) -> str | None:
    fp = question_fingerprint(question_text)
    for keyword, field in _AUTO_FILL_FINGERPRINTS.items():
        if keyword in fp:
            return field
    return None


def _profile_value_for_field(profile: Profile, field: str) -> str | None:
    raw = getattr(profile, field, None)
    if raw is None:
        return None
    if isinstance(raw, datetime | date):
        return raw.isoformat()
    return str(raw.value if hasattr(raw, "value") else raw)


async def answer_screeners(
    session: AsyncSession,
    application: Application,
    *,
    settings: Settings,
    job: Job | None = None,
    questions: Iterable[dict[str, Any]] | None = None,
    system: str | None = None,
    cache_system: bool = False,
) -> list[ApplicationScreenerAnswer]:
    """Populate / refresh ApplicationScreenerAnswer rows for `application`.

    `questions` is the ordered list of `{question_text, question_type,
    choices?, required?}` dicts extracted by the scraper. If omitted, the
    function works with whatever `ApplicationScreenerAnswer` rows already
    exist on the application (auto-fill / draft loop).

    Each row carries `source` + `drafted_by_model` + `reviewed_at` per
    DATA_MODEL.md § J. Auto-fills set `reviewed_at = utcnow()`; AI-drafts
    leave it null until user reviews.
    """
    user_id = application.user_id
    if await is_cost_capped(session, user_id, settings):
        raise CostCapExceededError("daily_llm_cost_cap_usd reached")

    profile_row = (
        await session.exec(
            select(Profile).where(Profile.user_id == user_id, Profile.deleted_at.is_(None))
        )
    ).one_or_none()
    if profile_row is None:
        raise ValueError(f"no profile for user_id={user_id}")
    if job is None and application.job_id is not None:
        job = (await session.exec(select(Job).where(Job.id == application.job_id))).one_or_none()

    # Pull existing rows so we can update in-place where appropriate.
    existing = (
        await session.exec(
            select(ApplicationScreenerAnswer).where(
                ApplicationScreenerAnswer.application_id == application.id
            )
        )
    ).all()
    by_fp = {row.question_fingerprint: row for row in existing}

    questions_list: list[dict[str, Any]] = list(questions or [])
    if not questions_list:
        # Use existing rows as the question list.
        for row in existing:
            questions_list.append(
                {
                    "question_text": row.question_text,
                    "question_type": row.question_type,
                    "choices": row.choices,
                    "required": row.required,
                    "order_index": row.order_index,
                }
            )

    out_rows: list[ApplicationScreenerAnswer] = []
    provider: LLMProvider | None = None  # Lazy — only instantiate if drafting needed.
    now = datetime.now(UTC)

    def _ensure_provider() -> LLMProvider:
        nonlocal provider
        if provider is None:
            provider = get_provider(settings)
        return provider

    for idx, q in enumerate(questions_list):
        text = q["question_text"]
        fp = question_fingerprint(text)
        qtype = q.get("question_type") or ScreenerQuestionType.TEXTAREA
        if isinstance(qtype, str):
            try:
                qtype = ScreenerQuestionType(qtype)
            except ValueError:
                qtype = ScreenerQuestionType.TEXTAREA
        choices = q.get("choices") or None
        required = bool(q.get("required", True))
        order_index = int(q.get("order_index", idx))

        row = by_fp.get(fp)
        # If existing row is USER-edited, preserve untouched.
        if row is not None and row.source == ScreenerAnswerSource.USER:
            out_rows.append(row)
            continue
        # Decide source: AUTO if a Profile field matches; DRAFTED otherwise.
        auto_field = _auto_field_for_question(text)
        if auto_field:
            answer_value = _profile_value_for_field(profile_row, auto_field)
            source = ScreenerAnswerSource.AUTO
            reviewed_at = now
            drafted_by_model = None
        else:
            # Plan 61 (0.2.7.14) — check the per-user reuse cache before
            # spending LLM tokens. A hit prefills the suggestion but never
            # auto-submits (decision D7); the row's `drafted_by_model` carries
            # a `reuse:<id>` marker so the UI swaps in the diff component.
            from services import profile_answer_service as _pas

            reuse_hit = None
            try:
                reuse_hit = await _pas.get_suggestion(
                    session,
                    user_id=user_id,
                    question_text=text,
                    company_name=application.company,
                )
            except Exception as exc:  # noqa: BLE001 — reuse lookup is best-effort
                log.debug("profile_answer reuse lookup failed: %s", exc)

            if reuse_hit is not None:
                answer_value = reuse_hit.answer
                source = ScreenerAnswerSource.DRAFTED
                reviewed_at = None
                drafted_by_model = f"reuse:{reuse_hit.id}"
            else:
                try:
                    p = _ensure_provider()
                    result = await llm_tracker.tracked_call(
                        session=session,
                        user_id=user_id,
                        provider=p,
                        method="structured",
                        prompt_name="answer_screener",
                        application_id=application.id,
                        prompt=_render_screener_prompt(
                            profile_row, job, text, qtype.value, choices
                        ),
                        schema=__import__(
                            "llm.prompts.answer_screener", fromlist=["ScreenerAnswer"]
                        ).ScreenerAnswer,
                        system=system,
                        cache_system=cache_system,
                    )
                    answer_value = str(result.value.get("answer") or "")
                except LLMProviderError as exc:
                    log.warning("answer_screener LLM failed for %r: %s", text, exc)
                    answer_value = ""
                source = ScreenerAnswerSource.DRAFTED
                reviewed_at = None
                drafted_by_model = provider.model_name if provider else None

        if row is None:
            row = ApplicationScreenerAnswer(
                application_id=application.id,
                question_text=text,
                question_fingerprint=fp,
                question_type=qtype,
                choices=list(choices) if choices else None,
                required=required,
                order_index=order_index,
                answer=answer_value,
                source=source,
                drafted_by_model=drafted_by_model,
                reviewed_at=reviewed_at,
            )
        else:
            row.question_text = text
            row.question_type = qtype
            row.choices = list(choices) if choices else None
            row.required = required
            row.order_index = order_index
            row.answer = answer_value
            row.source = source
            row.drafted_by_model = drafted_by_model
            row.reviewed_at = reviewed_at
            row.updated_at = now
        session.add(row)
        out_rows.append(row)

    await session.flush()
    return out_rows


def _render_screener_prompt(
    profile: Profile,
    job: Job | None,
    question_text: str,
    question_type: str,
    choices: list[str] | None,
) -> str:
    job_str = f"{job.company} — {job.role}" if job is not None else "(no job context)"
    choices_str = f"Choices: {choices}" if choices else ""
    return (
        f"Draft an answer for this screener question.\n\n"
        f"Candidate: {profile.full_name}\n"
        f"{profile.summary_short or ''}\n\n"
        f"Job: {job_str}\n\n"
        f"Question: {question_text}\n"
        f"Question type: {question_type}\n"
        f"{choices_str}\n\n"
        "Return ScreenerAnswer with answer + confidence."
    )


# ── pre_generate (resume + letter + screeners) ─────────────────────────


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
        if await is_cost_capped(session, application.user_id, settings):
            return PreGenerateResult(skipped_reason="cost_cap_reached")
        if await can_reuse_existing_resume(session, application, job):
            return PreGenerateResult(skipped_reason="reuse_heuristic")

    resume = await generate_resume(session, application, settings=settings, job=job)
    cover = await generate_cover_letter(session, application, settings=settings, job=job)
    screeners = await answer_screeners(session, application, settings=settings, job=job)
    return PreGenerateResult(resume=resume, cover_letter=cover, screeners=screeners)


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
    snap = await load_profile_snapshot(session, user_id)
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
    try:
        result = await typst_compile("onepage", data, output_path)
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


# ── Maintenance: stale-doc cleanup (cron) ──────────────────────────────


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
