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
from dataclasses import dataclass, field
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
    Certification,
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
    projects: list[Project]  # kind == "project" only
    open_source: list[Project] = field(default_factory=list)  # kind == "open_source"
    certifications: list[Certification] = field(default_factory=list)


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
    all_projects = (
        await session.exec(
            select(Project)
            .where(Project.profile_id == profile.id, Project.deleted_at.is_(None))
            .order_by(Project.order_index)
        )
    ).all()
    certifications = (
        await session.exec(
            select(Certification)
            .where(Certification.profile_id == profile.id)
            .order_by(Certification.order_index)
        )
    ).all()
    return ProfileSnapshot(
        profile=profile,
        experiences=experiences,
        bullets_by_experience=bullets_by_exp,
        skills=skills,
        education=education,
        projects=[p for p in all_projects if getattr(p, "kind", "project") != "open_source"],
        open_source=[p for p in all_projects if getattr(p, "kind", "project") == "open_source"],
        certifications=certifications,
    )


def _bullet_inventory(snap: ProfileSnapshot) -> list[Bullet]:
    return [b for bs in snap.bullets_by_experience.values() for b in bs]


# ── Bullet selection (pre-LLM honoring overrides) ───────────────────────


def _resolve_override(
    bullet: Bullet,
    application_overrides: dict[int, str] | None,
) -> BulletSelectionOverride | None:
    """Per-app `bullet_overrides` win over `Bullet.selection_override` (plan 86 / 0.4.5.08).

    Architect R2 round 2 — `PUT /api/v1/applications/{id}/bullet-override`
    writes `submission_artifacts["bullet_overrides"][<str(bid)>]` but the
    document generator previously ignored that dict. Resolution order per
    bullet:
      1. Per-app override (`always_include` / `never_include`) wins.
      2. Model column `Bullet.selection_override`.
      3. `None` (LLM picks).
    Unknown override values silently fall through to the model column —
    defense-in-depth in case future enum additions ship before this resolver.
    """
    if application_overrides:
        raw = application_overrides.get(bullet.id)
        if raw == BulletSelectionOverride.ALWAYS_INCLUDE.value:
            return BulletSelectionOverride.ALWAYS_INCLUDE
        if raw == BulletSelectionOverride.NEVER_INCLUDE.value:
            return BulletSelectionOverride.NEVER_INCLUDE
    return bullet.selection_override


def _split_bullets_by_override(
    bullets: list[Bullet],
    application_overrides: dict[int, str] | None = None,
) -> tuple[list[Bullet], list[Bullet], list[Bullet]]:
    always: list[Bullet] = []
    never: list[Bullet] = []
    auto: list[Bullet] = []
    for b in bullets:
        effective = _resolve_override(b, application_overrides)
        if effective == BulletSelectionOverride.ALWAYS_INCLUDE:
            always.append(b)
        elif effective == BulletSelectionOverride.NEVER_INCLUDE:
            never.append(b)
        else:
            auto.append(b)
    return always, never, auto


async def _ai_rank_bullets(
    *,
    session: AsyncSession,
    settings: Settings,
    snap: ProfileSnapshot,
    job: Job,
    user_id: int,
    application_id: int | None,
    system: str | None = None,
    cache_system: bool = False,
    application_overrides: dict[int, str] | None = None,
) -> list[int]:
    """Return the FULL bullet inventory in priority order, honoring overrides.

    `always_include` bullets lead (profile order); the LLM ranks the rest;
    `never_include` bullets are excluded. The page-fit loop packs from the
    head of this list and drops from the tail.

    `application_overrides` (plan 86 / 0.4.5.08) — per-application bullet
    overrides keyed by bullet id, values `"always_include"` / `"never_include"`.
    Win over the model-level `Bullet.selection_override` column.
    """
    inventory = _bullet_inventory(snap)
    if not inventory:
        return []
    always, never, auto = _split_bullets_by_override(inventory, application_overrides)
    del never

    ranked: list[int] = [b.id for b in always]
    if not auto:
        return ranked

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
            prompt=_render_rank_prompt(bullet_payload, job_payload),
            schema=__import__(
                "llm.prompts.select_bullets", fromlist=["BulletSelection"]
            ).BulletSelection,
            system=system,
            cache_system=cache_system,
        )
        chosen = list(result.value.get("selected_ids", [])) if result else []
    except LLMProviderError as exc:
        log.warning("select_bullets LLM failed; falling back to profile order: %s", exc)
        chosen = [b.id for b in auto]
    # Defend against the model returning ids outside the auto pool, and
    # re-append anything it omitted so no bullet silently vanishes from the
    # candidate pool (it can still be dropped by the page-fit loop).
    auto_ids = {b.id for b in auto}
    seen: set[int] = set()
    cleaned: list[int] = []
    for cid in chosen:
        if cid in auto_ids and cid not in seen:
            seen.add(cid)
            cleaned.append(cid)
    for b in auto:
        if b.id not in seen:
            cleaned.append(b.id)
    ranked.extend(cleaned)
    return ranked


def _render_rank_prompt(bullets: list[dict], job: dict) -> str:
    from llm.prompts.select_bullets import PROMPT as RANK_PROMPT

    lines = "\n".join(f"{b['id']} → {b['text']}" for b in bullets)
    return RANK_PROMPT.format(
        bullets=lines,
        role=job.get("role", ""),
        description=(job.get("description") or "")[:1500],
        skills=", ".join(job.get("skills_required", [])),
    )


async def _tailor_summary(
    *,
    session: AsyncSession,
    settings: Settings,
    snap: ProfileSnapshot,
    job: Job,
    user_id: int,
    application_id: int | None,
    ranked_bullet_ids: list[int],
    system: str | None = None,
    cache_system: bool = False,
) -> str | None:
    """JD-tailored 2–3 line summary pitch. Falls back to the profile summary."""
    from llm.prompts.tailor_summary import TailoredSummary, render_prompt

    p = snap.profile
    fallback = p.summary_short or p.summary_full
    by_id = {b.id: b for b in _bullet_inventory(snap)}
    top_bullets = [by_id[bid].text for bid in ranked_bullet_ids[:8] if bid in by_id]
    profile_text = (
        f"Headline: {p.headline or '(none)'}\n"
        f"Current summary: {fallback or '(none)'}\n"
        f"Skills: {', '.join(item for s in snap.skills for item in (s.items or [])[:6])[:400]}"
    )
    job_text = (
        f"{job.company} — {job.role}\n{(job.description or job.description_html or '')[:1500]}"
    )
    try:
        provider = get_provider(settings)
        result = await llm_tracker.tracked_call(
            session=session,
            user_id=user_id,
            provider=provider,
            method="structured",
            prompt_name="tailor_summary",
            application_id=application_id,
            prompt=render_prompt(
                name=p.full_name, profile_text=profile_text, bullets=top_bullets, job_text=job_text
            ),
            schema=TailoredSummary,
            system=system,
            cache_system=cache_system,
        )
        summary = str(result.value.get("summary") or "").strip()
        return summary or fallback
    except LLMProviderError as exc:
        log.warning("tailor_summary failed; using profile summary: %s", exc)
        return fallback


# ── Resume generation ───────────────────────────────────────────────────


# One printed line in `onepage.typ` (10pt New Computer Modern, 0.3in
# margins, ∘ + 0.15in list indent, justified) holds ~125+ characters — the
# cv.tex reference's longest bullet (127 chars) fits on one line. The
# refine TARGET stays 112 with capacity 118: both are safely under the true
# wrap point, and the eval harness checks capacity, not the target — a
# 115-char line renders fine and shouldn't be flagged.
RESUME_BULLET_CHAR_BUDGET = 112
RESUME_BULLET_LINE_CAPACITY = 118

# JD excerpt cap for the per-bullet refine prompt — full JDs blow up the
# token bill × ~20 bullets per generation.
_REFINE_JD_CHARS = 2400


async def _refine_one_bullet(
    *,
    session: AsyncSession,
    settings: Settings,
    user_id: int,
    application_id: int | None,
    bullet: Bullet,
    job_text: str,
    target_chars: int = RESUME_BULLET_CHAR_BUDGET,
    system: str | None = None,
    cache_system: bool = False,
) -> str:
    """Rewrite one bullet against the JD (mirror truthful terminology) AND
    enforce the one-line character budget.

    Every selected bullet goes through one refine call; a result over
    budget gets ONE stricter retry, then falls back to the shorter of the
    two candidates (the page-fit loop + eval scorecard catch stragglers).
    LLM failure degrades to plain truncation of the original.
    """
    from llm.prompts.refine_bullet import PROMPT as REFINE_PROMPT
    from llm.prompts.refine_bullet import RefinedBullet

    provider = get_provider(settings)

    async def _call(target: int, text: str) -> str | None:
        try:
            result = await llm_tracker.tracked_call(
                session=session,
                user_id=user_id,
                provider=provider,
                method="structured",
                prompt_name="refine_bullet",
                application_id=application_id,
                prompt=REFINE_PROMPT.format(
                    job_text=job_text[:_REFINE_JD_CHARS], text=text, target_chars=target
                ),
                schema=RefinedBullet,
                system=system,
                cache_system=cache_system,
            )
            refined = str(result.value.get("refined") or "").strip()
            return refined or None
        except LLMProviderError as exc:
            log.warning("refine_bullet failed: %s", exc)
            return None

    first = await _call(target_chars, bullet.text)
    if first is None:
        # No provider / hard failure — degrade honestly to a trim.
        if len(bullet.text) <= target_chars:
            return bullet.text
        return bullet.text[: target_chars - 1] + "…"
    if len(first) <= target_chars:
        return first
    second = await _call(int(target_chars * 0.9), first)
    candidates = [c for c in (first, second) if c]
    fitting = [c for c in candidates if len(c) <= target_chars]
    if fitting:
        return fitting[0]
    return min(candidates, key=len)


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


def _select_template(application: Application, settings: Settings) -> tuple[str, str | None]:
    """One template (`onepage.typ`) for every board — it is both the dense
    recruiter-standard layout AND ATS-safe (single column, ligatures off,
    plain bullets). Returns ``(template_name, pdf_standard)``; ATS-known
    boards keep PDF/A-1b output for maximum parser compatibility.
    """
    del settings  # `resume_template_preference` is vestigial post-consolidation
    board = getattr(application, "board", None)
    if board is not None and board in _ATS_BOARDS:
        return "onepage", "a-1b"
    return "onepage", None


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
RESUME_MAX_FIT_ATTEMPTS = 14
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

    out_dir = _app_documents_dir(application.id)
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
    for _attempt in range(RESUME_MAX_FIT_ATTEMPTS):
        data = await _build_resume_data(
            snap=snap,
            selected_bullet_ids=candidate_ids,
            trimmed=trimmed,
            tailored_summary=tailored_summary,
            excluded_project_ids=excluded_projects,
            excluded_certification_ids=excluded_certs,
        )
        try:
            result = await typst_compile(template_name, data, out_pdf, pdf_standard=pdf_standard)
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
    else:
        final_result = result

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
                result = await typst_compile(
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
                final_result = await typst_compile(
                    template_name, data, out_pdf, pdf_standard=pdf_standard
                )
            except TypstError as exc:  # pragma: no cover — compiled moments ago
                log.warning("post-add-back recompile failed: %s", exc)
        if added_back:
            log.info("density add-back kept %d extra bullets", len(added_back))

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
            "ranked_ids": ranked_ids,
            "dropped_for_fit": dropped_for_fit,
            "dropped_sections": dropped_sections,
            "added_back": added_back,
            "summary": tailored_summary,
            "trimmed_lines": {str(k): v for k, v in trimmed.items()},
            "jd_hash": _hash_jd(job.description_html or job.description),
        },
    )
    session.add(doc)
    await session.flush()
    return doc


# ── Workspace edit recompiles (item 2, 2026-07) ─────────────────────────
# The review workspace lets the user edit a tailored bullet's text and
# toggle include/exclude for THIS application, then see the PDF update.
# These recompile paths are LLM-free: they reuse the latest generated
# document's selection + refined lines, layer the per-app overrides on
# top, and re-run only the Typst compile.


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
    doc = await _latest_error_free_doc(session, application.id, GeneratedDocumentKind.RESUME)
    if doc is None or not doc.bullet_selection:
        return None
    snap = await load_profile_snapshot(session, application.user_id)
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
    out_pdf = _app_documents_dir(application.id) / "resume.pdf"
    data = await _build_resume_data(
        snap=snap,
        selected_bullet_ids=effective,
        trimmed=texts,
        tailored_summary=(blob.get("summary") or None),
        excluded_project_ids=excluded_projects,
        excluded_certification_ids=excluded_certs,
    )
    result = await typst_compile(template_name, data, out_pdf, pdf_standard=pdf_standard)

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
    doc = await _latest_error_free_doc(session, application.id, GeneratedDocumentKind.COVER_LETTER)
    if doc is None or not doc.bullet_selection:
        return None
    sections = doc.bullet_selection.get("sections")
    if not isinstance(sections, dict):
        return None
    snap = await load_profile_snapshot(session, application.user_id)
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
    out_pdf = _app_documents_dir(application.id) / "cover-letter.pdf"
    result = await typst_compile("cover_letter", typst_data, out_pdf)
    doc.byte_size = result.byte_size
    doc.page_count = result.page_count
    doc.compiled_at = result.compiled_at
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
    profile_str = (
        f"{profile.get('full_name', '')}\n"
        f"{profile.get('summary_short') or profile.get('summary_full', '')}\n"
        f"Top bullets: {'; '.join(top_bullets)[:1500]}"
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
    for keyword, field_name in _AUTO_FILL_FINGERPRINTS.items():
        if keyword in fp:
            return field_name
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
