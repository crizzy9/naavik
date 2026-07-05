"""Profile service partial — Wave 4 of plan 10 § B.7.

Wave 4 ships: get_profile, update_field (per-field PUT), update_application_questions,
add_bullet, update_bullet, delete_bullet (soft), reorder_bullets. Wave 6 adds
extract_resume_to_profile + AI tag inference + AppEvent emission for `profile_updated`.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import (
    AppEvent,
    AppEventKind,
    Bullet,
    Certification,
    Education,
    Experience,
    Profile,
    Project,
    Skill,
)

# Distinguishes "kwarg omitted" from an explicit None (which is a real value
# for nullable fields like Bullet.selection_override).
_UNSET: Any = object()


def _pkg():
    """The `services.profile` package surface, resolved at call time.

    Intra-module calls to shimmed/patched seams (`get_profile`,
    `get_bullet`, `get_bullets_for_experience`, `get_experience`,
    `parse_resume_heuristics`) route through the package `__init__` so
    conftest shims and `patch("services.profile.X")` keep intercepting
    them — pre-split they read this module's own globals, which WAS the
    patch surface (plan 92 B4)."""
    from services import profile

    return profile


# Whitelist of profile fields that the per-field PUT endpoint may touch.
# (Same set as the route handler's `_ALLOWED_FIELDS`; service-side gate is
# the source of truth.)
ALLOWED_PROFILE_FIELDS = frozenset(
    {
        "full_name",
        "headline",
        "current_company",
        "location",
        "email",
        "phone",
        "portfolio_url",
        "github_handle",
        "linkedin_handle",
        "summary_full",
        "summary_short",
        "open_to_opportunities",
        "work_authorization",
        "visa_sponsorship_needed",
        "willing_to_relocate",
        "notice_period_days",
        "salary_expectation_usd",
        "earliest_start",
        "veteran_status",
        "disability_status",
        "race_ethnicity",
        "gender_identity",
    }
)


# ── Read ─────────────────────────────────────────────────────────────────


async def get_profile(session: AsyncSession, user_id: int) -> Profile | None:
    stmt = select(Profile).where(
        Profile.user_id == user_id,
        Profile.deleted_at.is_(None),
    )
    return (await session.exec(stmt)).one_or_none()


async def get_score_history(session: AsyncSession, user_id: int) -> dict:
    """Plan 73 (0.3.2.03) — read `Profile.score_history` blob for sparkline.

    Empty dict when no Profile row OR the column is still default. Cron
    `score.aggregate_daily` keeps this fresh; ctx-builder consumes it.
    """
    profile = await _pkg().get_profile(session, user_id)
    if profile is None:
        return {}
    return dict(profile.score_history or {})


async def get_experience(session: AsyncSession, experience_id: int) -> Experience | None:
    stmt = select(Experience).where(
        Experience.id == experience_id,
        Experience.deleted_at.is_(None),
    )
    return (await session.exec(stmt)).one_or_none()


async def get_bullets_for_experience(session: AsyncSession, experience_id: int) -> list[Bullet]:
    stmt = (
        select(Bullet)
        .where(Bullet.experience_id == experience_id, Bullet.deleted_at.is_(None))
        .order_by(Bullet.order_index)
    )
    return (await session.exec(stmt)).all()


async def get_bullet(session: AsyncSession, bullet_id: int) -> Bullet | None:
    stmt = select(Bullet).where(
        Bullet.id == bullet_id,
        Bullet.deleted_at.is_(None),
    )
    return (await session.exec(stmt)).one_or_none()


async def owns_bullet(session: AsyncSession, *, bullet_id: int, user_id: int) -> bool:
    """True iff `bullet_id` belongs to `user_id` (bullet → experience → profile).

    IDOR guard for the `/api/v1/bullets/*` mutation endpoints. Bullets carry
    no direct `user_id`; ownership is resolved through the
    Bullet → Experience → Profile chain.
    """
    stmt = (
        select(Bullet.id)
        .join(Experience, Experience.id == Bullet.experience_id)
        .join(Profile, Profile.id == Experience.profile_id)
        .where(
            Bullet.id == bullet_id,
            Bullet.deleted_at.is_(None),
            Profile.user_id == user_id,
            Profile.deleted_at.is_(None),
        )
    )
    return (await session.exec(stmt)).one_or_none() is not None


async def owns_experience(session: AsyncSession, *, experience_id: int, user_id: int) -> bool:
    """True iff `experience_id` belongs to `user_id` (experience → profile).

    IDOR guard for `POST /api/v1/bullets` (bullet creation targets an
    experience the caller must own).
    """
    stmt = (
        select(Experience.id)
        .join(Profile, Profile.id == Experience.profile_id)
        .where(
            Experience.id == experience_id,
            Experience.deleted_at.is_(None),
            Profile.user_id == user_id,
            Profile.deleted_at.is_(None),
        )
    )
    return (await session.exec(stmt)).one_or_none() is not None


# Plan 60 / 0.2.7.17 — list accessors used to live in `src/db/sample_data.py`.
# Replacements consume an AsyncSession + user_id; each joins via Profile
# (`Profile.user_id == user_id`) since the children carry `profile_id` rather
# than a direct `user_id` column. Soft-delete-aware where the column exists
# (Experience / Bullet / Project carry `deleted_at`; Skill / Education /
# Certification don't).


async def list_experiences(session: AsyncSession, user_id: int) -> list[Experience]:
    stmt = (
        select(Experience)
        .join(Profile, Profile.id == Experience.profile_id)
        .where(
            Profile.user_id == user_id,
            Profile.deleted_at.is_(None),
            Experience.deleted_at.is_(None),
        )
        .order_by(Experience.order_index)
    )
    rows = (await session.exec(stmt)).all()
    return list(rows)


async def list_all_bullets(session: AsyncSession, user_id: int) -> list[Bullet]:
    """All live bullets for the user across all experiences."""
    stmt = (
        select(Bullet)
        .join(Experience, Experience.id == Bullet.experience_id)
        .join(Profile, Profile.id == Experience.profile_id)
        .where(
            Profile.user_id == user_id,
            Profile.deleted_at.is_(None),
            Experience.deleted_at.is_(None),
            Bullet.deleted_at.is_(None),
        )
        .order_by(Bullet.order_index)
    )
    rows = (await session.exec(stmt)).all()
    return list(rows)


async def list_skills(session: AsyncSession, user_id: int) -> list[Skill]:
    stmt = (
        select(Skill)
        .join(Profile, Profile.id == Skill.profile_id)
        .where(Profile.user_id == user_id, Profile.deleted_at.is_(None))
        .order_by(Skill.order_index)
    )
    rows = (await session.exec(stmt)).all()
    return list(rows)


async def list_educations(session: AsyncSession, user_id: int) -> list[Education]:
    stmt = (
        select(Education)
        .join(Profile, Profile.id == Education.profile_id)
        .where(Profile.user_id == user_id, Profile.deleted_at.is_(None))
        .order_by(Education.order_index)
    )
    rows = (await session.exec(stmt)).all()
    return list(rows)


async def list_projects(session: AsyncSession, user_id: int) -> list[Project]:
    stmt = (
        select(Project)
        .join(Profile, Profile.id == Project.profile_id)
        .where(
            Profile.user_id == user_id,
            Profile.deleted_at.is_(None),
            Project.deleted_at.is_(None),
        )
        .order_by(Project.order_index)
    )
    rows = (await session.exec(stmt)).all()
    return list(rows)


async def list_certifications(session: AsyncSession, user_id: int) -> list[Certification]:
    stmt = (
        select(Certification)
        .join(Profile, Profile.id == Certification.profile_id)
        .where(Profile.user_id == user_id, Profile.deleted_at.is_(None))
        .order_by(Certification.order_index)
    )
    rows = (await session.exec(stmt)).all()
    return list(rows)


# ── Profile mutations ────────────────────────────────────────────────────


async def update_field(
    session: AsyncSession,
    user_id: int,
    field: str,
    value: Any,
) -> Profile:
    """Per-field PUT for the autosave indicator."""
    if field not in ALLOWED_PROFILE_FIELDS:
        raise ValueError(f"field {field!r} not allowed via per-field PUT")
    profile = await _pkg().get_profile(session, user_id)
    if profile is None:
        raise LookupError(f"no profile for user_id={user_id}")
    setattr(profile, field, value)
    profile.updated_at = datetime.now(UTC)
    session.add(profile)
    await _emit_profile_updated(session, user_id, [field])
    await session.flush()
    # Plan 65 § D.3 (OQ-6): best-effort on-edit profile embedding refresh.
    # Gated by Settings.semantic_match_enabled inside the helper; errors
    # swallowed (nightly cron is the safety net).
    from services.scorer.embeddings import maybe_refresh_profile_embedding

    await maybe_refresh_profile_embedding(session, user_id=user_id)
    return profile


# Plan 0.7.0.48 W3 hacker HIGH fold-in (2026-05-25): bounded quantifiers
# on email/phone regexes + 32 KB input truncation defense-in-depth. The
# previous unbounded `[\w.+-]+@[\w-]+\.[\w.-]+` showed catastrophic
# backtracking on adversarial PDF text (measured: 20 KB alpha → 0.8 s;
# 100 KB → 19.6 s, blocking the async event loop in C). Combined with
# the now-open signup, any unauth visitor could DoS the instance via a
# crafted PDF upload. Bounds match RFC 5321 local-part (64) + domain
# label (63 per label, 253 total) + TLD (63). Phone capped per E.164
# practical limit (15 digits + ~10 separators).
_HEURISTIC_INPUT_CAP = 32 * 1024  # 32 KB — defense-in-depth truncation
_EMAIL_RE = re.compile(r"[\w.+-]{1,64}@[\w-]{1,255}\.[\w.-]{1,255}")
_PHONE_RE = re.compile(r"(\+?\d[\d\s\-().]{8,30}\d)")
_NAME_ALLOWED_RE = re.compile(r"^[A-Za-z][A-Za-z\s\-'.]{0,59}$")


def parse_resume_heuristics(text: str) -> dict[str, str]:
    """Pure regex extract of email / phone / name from raw resume text.

    Returns a dict with keys present only when a candidate was found. The
    caller decides whether to populate (we never overwrite operator edits
    in `set_raw_resume_text`).

    Input is truncated to `_HEURISTIC_INPUT_CAP` before any regex runs —
    defense in depth on top of the bounded quantifiers above. A real
    resume's first-page email/name/phone sits well within 32 KB.
    """
    out: dict[str, str] = {}
    if not text:
        return out
    if len(text) > _HEURISTIC_INPUT_CAP:
        text = text[:_HEURISTIC_INPUT_CAP]
    if m := _EMAIL_RE.search(text):
        out["email"] = m.group(0)
    if m := _PHONE_RE.search(text):
        out["phone"] = m.group(1).strip()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or len(line) > 60:
            continue
        if "@" in line or any(ch.isdigit() for ch in line):
            continue
        if _NAME_ALLOWED_RE.match(line):
            out["full_name"] = line
            break
    return out


async def set_raw_resume_text(
    session: AsyncSession,
    user_id: int,
    text: str,
) -> Profile | None:
    """Persist `text` as `Profile.raw_resume_text` + heuristically populate
    empty identity fields (full_name, email, phone) from regex matches.

    Won't overwrite operator hand-edits — only fills fields that are
    currently falsy. Returns the updated Profile, or None when the user has
    no Profile row yet (best-effort; caller can ignore).
    """
    profile = await _pkg().get_profile(session, user_id)
    if profile is None:
        return None
    profile.raw_resume_text = text
    parsed = _pkg().parse_resume_heuristics(text)
    for field in ("full_name", "email", "phone"):
        if parsed.get(field) and not getattr(profile, field, None):
            setattr(profile, field, parsed[field])
    profile.updated_at = datetime.now(UTC)
    session.add(profile)
    await session.flush()
    return profile


async def update_application_questions(
    session: AsyncSession,
    user_id: int,
    payload: dict[str, Any],
) -> Profile:
    """Bulk update for the 10 EEO/visa fields per DATA_MODEL.md § A note."""
    profile = await _pkg().get_profile(session, user_id)
    if profile is None:
        raise LookupError(f"no profile for user_id={user_id}")

    eeo_fields = {
        "work_authorization",
        "visa_sponsorship_needed",
        "willing_to_relocate",
        "notice_period_days",
        "salary_expectation_usd",
        "earliest_start",
        "veteran_status",
        "disability_status",
        "race_ethnicity",
        "gender_identity",
    }
    touched: list[str] = []
    for k, v in payload.items():
        if k in eeo_fields:
            setattr(profile, k, v)
            touched.append(k)
    if touched:
        profile.updated_at = datetime.now(UTC)
        session.add(profile)
        await _emit_profile_updated(session, user_id, touched)
        await session.flush()
        # Plan 65 § D.3 (OQ-6): best-effort on-edit profile embedding.
        from services.scorer.embeddings import maybe_refresh_profile_embedding

        await maybe_refresh_profile_embedding(session, user_id=user_id)
    return profile


# ── Bullet ops ───────────────────────────────────────────────────────────


async def add_bullet(
    session: AsyncSession,
    *,
    experience_id: int,
    text: str,
    tags: list[str] | None = None,
) -> Bullet:
    now = datetime.now(UTC)
    b = Bullet(
        experience_id=experience_id,
        text=text or "New bullet — edit to write the long version.",
        tags=list(tags or []),
        edited_at=now,
        order_index=999,  # tail of list; reorder normalizes
        created_at=now,
        updated_at=now,
    )
    session.add(b)
    await session.flush()
    return b


async def update_bullet(
    session: AsyncSession,
    bullet_id: int,
    *,
    text: str | None = None,
    tags: list[str] | None = None,
    selection_override: Any = _UNSET,
) -> Bullet:
    b = await _pkg().get_bullet(session, bullet_id)
    if b is None:
        raise LookupError(f"bullet {bullet_id} not found")
    if text is not None:
        b.text = text
    if tags is not None:
        b.tags = list(tags)
    # None is a real value here (clear back to "AI decides"); omitting the
    # kwarg means "leave unchanged" — hence the sentinel default.
    if selection_override is not _UNSET:
        b.selection_override = selection_override
    now = datetime.now(UTC)
    b.edited_at = now
    b.updated_at = now
    session.add(b)
    await session.flush()
    # Plan 65 § D.3 (OQ-6): bullet-level edits also re-embed the profile.
    # Resolve owning user_id via experience → profile chain.
    exp = (
        await session.exec(select(Experience).where(Experience.id == b.experience_id))
    ).one_or_none()
    if exp is not None:
        prof = (
            await session.exec(select(Profile).where(Profile.id == exp.profile_id))
        ).one_or_none()
        if prof is not None:
            from services.scorer.embeddings import maybe_refresh_profile_embedding

            await maybe_refresh_profile_embedding(session, user_id=prof.user_id)
    return b


async def delete_bullet(session: AsyncSession, bullet_id: int) -> bool:
    b = await _pkg().get_bullet(session, bullet_id)
    if b is None:
        return False
    now = datetime.now(UTC)
    b.deleted_at = now
    b.updated_at = now
    session.add(b)
    await session.flush()
    return True


async def reorder_bullets(
    session: AsyncSession,
    *,
    experience_id: int,
    bullet_ids: list[int],
) -> list[Bullet]:
    """Apply order_index from the provided list."""
    bullets = await _pkg().get_bullets_for_experience(session, experience_id)
    by_id = {b.id: b for b in bullets}
    now = datetime.now(UTC)
    for idx, bid in enumerate(bullet_ids):
        b = by_id.get(bid)
        if b is None:
            continue
        b.order_index = idx
        b.updated_at = now
        session.add(b)
    await session.flush()
    return await _pkg().get_bullets_for_experience(session, experience_id)


# ── Dossier child-entity CRUD (item 1, 2026-07) ─────────────────────────
# Experiences / education / projects / skills / certifications used to be
# parse-only (resume upload was the sole writer). The profile editor is now
# fully self-serve: add/remove slots + per-field edits via the bulk PUT.
# Soft-delete where the column exists (Experience / Project); hard-delete
# for Education / Skill / Certification (no deleted_at column).


async def _profile_or_raise(session: AsyncSession, user_id: int) -> Profile:
    profile = await _pkg().get_profile(session, user_id)
    if profile is None:
        raise LookupError(f"no profile for user_id={user_id}")
    return profile


def _owned_via_profile(model, entity_id_col):
    """Build a `select(entity.id).join(Profile)` ownership probe statement."""

    def _stmt(entity_id: int, user_id: int):
        stmt = (
            select(entity_id_col)
            .join(Profile, Profile.id == model.profile_id)
            .where(
                entity_id_col == entity_id,
                Profile.user_id == user_id,
                Profile.deleted_at.is_(None),
            )
        )
        if hasattr(model, "deleted_at"):
            stmt = stmt.where(model.deleted_at.is_(None))
        return stmt

    return _stmt


async def owns_education(session: AsyncSession, *, education_id: int, user_id: int) -> bool:
    stmt = _owned_via_profile(Education, Education.id)(education_id, user_id)
    return (await session.exec(stmt)).one_or_none() is not None


async def owns_project(session: AsyncSession, *, project_id: int, user_id: int) -> bool:
    stmt = _owned_via_profile(Project, Project.id)(project_id, user_id)
    return (await session.exec(stmt)).one_or_none() is not None


async def owns_skill(session: AsyncSession, *, skill_id: int, user_id: int) -> bool:
    stmt = _owned_via_profile(Skill, Skill.id)(skill_id, user_id)
    return (await session.exec(stmt)).one_or_none() is not None


async def owns_certification(session: AsyncSession, *, certification_id: int, user_id: int) -> bool:
    stmt = _owned_via_profile(Certification, Certification.id)(certification_id, user_id)
    return (await session.exec(stmt)).one_or_none() is not None


async def _next_order_index(session: AsyncSession, model, profile_id: int) -> int:
    stmt = select(model).where(model.profile_id == profile_id)
    rows = (await session.exec(stmt)).all()
    return max((r.order_index for r in rows), default=-1) + 1


async def add_experience(session: AsyncSession, user_id: int) -> Experience:
    profile = await _profile_or_raise(session, user_id)
    now = datetime.now(UTC)
    exp = Experience(
        profile_id=profile.id,
        company="New company",
        title="New role",
        start_date=now,
        order_index=await _next_order_index(session, Experience, profile.id),
        created_at=now,
        updated_at=now,
    )
    session.add(exp)
    await _emit_profile_updated(session, user_id, ["experience:add"])
    await session.flush()
    return exp


async def update_experience(
    session: AsyncSession,
    experience_id: int,
    *,
    company: str | None = None,
    title: str | None = None,
    team: str | None = None,
    location: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None | object = "__unset__",
) -> Experience:
    exp = await _pkg().get_experience(session, experience_id)
    if exp is None:
        raise LookupError(f"experience {experience_id} not found")
    if company is not None and company.strip():
        exp.company = company.strip()
    if title is not None and title.strip():
        exp.title = title.strip()
    if team is not None:
        exp.team = team.strip() or None
    if location is not None:
        exp.location = location.strip() or None
    if start_date is not None:
        exp.start_date = start_date
    if end_date != "__unset__":
        exp.end_date = end_date
    if exp.end_date is not None and exp.start_date is not None and exp.end_date <= exp.start_date:
        raise ValueError("end date must be after start date")
    exp.updated_at = datetime.now(UTC)
    session.add(exp)
    await session.flush()
    return exp


async def delete_experience(session: AsyncSession, experience_id: int) -> bool:
    exp = await _pkg().get_experience(session, experience_id)
    if exp is None:
        return False
    now = datetime.now(UTC)
    exp.deleted_at = now
    exp.updated_at = now
    session.add(exp)
    await session.flush()
    return True


async def add_education(session: AsyncSession, user_id: int) -> Education:
    profile = await _profile_or_raise(session, user_id)
    now = datetime.now(UTC)
    edu = Education(
        profile_id=profile.id,
        institution="New institution",
        degree="Degree",
        start_date=now,
        order_index=await _next_order_index(session, Education, profile.id),
        created_at=now,
        updated_at=now,
    )
    session.add(edu)
    await _emit_profile_updated(session, user_id, ["education:add"])
    await session.flush()
    return edu


async def update_education(
    session: AsyncSession,
    education_id: int,
    **fields: Any,
) -> Education:
    edu = await session.get(Education, education_id)
    if edu is None:
        raise LookupError(f"education {education_id} not found")
    for name in ("institution", "degree"):
        if (v := fields.get(name)) is not None and str(v).strip():
            setattr(edu, name, str(v).strip())
    for name in ("school", "location", "gpa"):
        if (v := fields.get(name)) is not None:
            setattr(edu, name, str(v).strip() or None)
    if (v := fields.get("start_date")) is not None:
        edu.start_date = v
    if "end_date" in fields:
        edu.end_date = fields["end_date"]
    edu.updated_at = datetime.now(UTC)
    session.add(edu)
    await session.flush()
    return edu


async def delete_education(session: AsyncSession, education_id: int) -> bool:
    edu = await session.get(Education, education_id)
    if edu is None:
        return False
    await session.delete(edu)
    await session.flush()
    return True


async def add_project(session: AsyncSession, user_id: int, *, kind: str = "project") -> Project:
    if kind not in {"project", "open_source"}:
        raise ValueError(f"unknown project kind {kind!r}")
    profile = await _profile_or_raise(session, user_id)
    now = datetime.now(UTC)
    proj = Project(
        profile_id=profile.id,
        kind=kind,
        title="New contribution" if kind == "open_source" else "New project",
        text="Describe what you built and its impact.",
        order_index=await _next_order_index(session, Project, profile.id),
        created_at=now,
        updated_at=now,
    )
    session.add(proj)
    await _emit_profile_updated(session, user_id, [f"{kind}:add"])
    await session.flush()
    return proj


async def update_project(
    session: AsyncSession,
    project_id: int,
    **fields: Any,
) -> Project:
    proj = await session.get(Project, project_id)
    if proj is None or proj.deleted_at is not None:
        raise LookupError(f"project {project_id} not found")
    if (v := fields.get("title")) is not None and str(v).strip():
        proj.title = str(v).strip()
    if (v := fields.get("text")) is not None and str(v).strip():
        proj.text = str(v).strip()
    if (v := fields.get("link")) is not None:
        proj.link = str(v).strip() or None
    if (v := fields.get("tags")) is not None:
        proj.tags = list(v)
    if "date" in fields:
        proj.date = fields["date"]
    # None is a real value ("AI decides") — presence in `fields` is the signal.
    if "selection_override" in fields:
        proj.selection_override = fields["selection_override"]
    proj.updated_at = datetime.now(UTC)
    session.add(proj)
    await session.flush()
    return proj


async def delete_project(session: AsyncSession, project_id: int) -> bool:
    proj = await session.get(Project, project_id)
    if proj is None or proj.deleted_at is not None:
        return False
    now = datetime.now(UTC)
    proj.deleted_at = now
    proj.updated_at = now
    session.add(proj)
    await session.flush()
    return True


async def add_skill(session: AsyncSession, user_id: int) -> Skill:
    profile = await _profile_or_raise(session, user_id)
    now = datetime.now(UTC)
    skill = Skill(
        profile_id=profile.id,
        category="New category",
        items=[],
        order_index=await _next_order_index(session, Skill, profile.id),
        created_at=now,
        updated_at=now,
    )
    session.add(skill)
    await _emit_profile_updated(session, user_id, ["skill:add"])
    await session.flush()
    return skill


async def update_skill(
    session: AsyncSession,
    skill_id: int,
    *,
    category: str | None = None,
    items: list[str] | None = None,
) -> Skill:
    skill = await session.get(Skill, skill_id)
    if skill is None:
        raise LookupError(f"skill {skill_id} not found")
    if category is not None and category.strip():
        skill.category = category.strip()
    if items is not None:
        skill.items = [i.strip() for i in items if i.strip()]
    skill.updated_at = datetime.now(UTC)
    session.add(skill)
    await session.flush()
    return skill


async def delete_skill(session: AsyncSession, skill_id: int) -> bool:
    skill = await session.get(Skill, skill_id)
    if skill is None:
        return False
    await session.delete(skill)
    await session.flush()
    return True


async def add_certification(session: AsyncSession, user_id: int) -> Certification:
    profile = await _profile_or_raise(session, user_id)
    now = datetime.now(UTC)
    cert = Certification(
        profile_id=profile.id,
        title="New certification",
        issuer="Issuer",
        order_index=await _next_order_index(session, Certification, profile.id),
        created_at=now,
        updated_at=now,
    )
    session.add(cert)
    await _emit_profile_updated(session, user_id, ["certification:add"])
    await session.flush()
    return cert


async def update_certification(
    session: AsyncSession,
    certification_id: int,
    **fields: Any,
) -> Certification:
    cert = await session.get(Certification, certification_id)
    if cert is None:
        raise LookupError(f"certification {certification_id} not found")
    for name in ("title", "issuer"):
        if (v := fields.get(name)) is not None and str(v).strip():
            setattr(cert, name, str(v).strip())
    if (v := fields.get("description")) is not None:
        cert.description = str(v).strip() or None
    if "date" in fields:
        cert.date = fields["date"]
    # None is a real value ("AI decides") — presence in `fields` is the signal.
    if "selection_override" in fields:
        cert.selection_override = fields["selection_override"]
    cert.updated_at = datetime.now(UTC)
    session.add(cert)
    await session.flush()
    return cert


async def delete_certification(session: AsyncSession, certification_id: int) -> bool:
    cert = await session.get(Certification, certification_id)
    if cert is None:
        return False
    await session.delete(cert)
    await session.flush()
    return True


# ── Internal: AppEvent emission ──────────────────────────────────────────


async def _emit_profile_updated(
    session: AsyncSession,
    user_id: int,
    fields_changed: list[str],
) -> None:
    """Fire `profile_updated` event for the portfolio_sync debouncer (Wave 6).

    Wave 4 records the event row; Wave 6 wires the debounced listener that
    regenerates the generic resume + Netlify rebuild.
    """
    ev = AppEvent(
        user_id=user_id,
        application_id=None,
        kind=AppEventKind.NOTE_ADDED,  # closest existing kind; Wave 6 may add a dedicated PROFILE_UPDATED kind
        occurred_at=datetime.now(UTC),
        payload={"fields_changed": fields_changed, "synthetic_kind": "profile_updated"},
        actor="profile_service",
    )
    session.add(ev)
