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
    profile = await get_profile(session, user_id)
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
    profile = await get_profile(session, user_id)
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
    from services.embedding_service import maybe_refresh_profile_embedding

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
    profile = await get_profile(session, user_id)
    if profile is None:
        return None
    profile.raw_resume_text = text
    parsed = parse_resume_heuristics(text)
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
    profile = await get_profile(session, user_id)
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
        from services.embedding_service import maybe_refresh_profile_embedding

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
    selection_override: Any | None = None,
) -> Bullet:
    b = await get_bullet(session, bullet_id)
    if b is None:
        raise LookupError(f"bullet {bullet_id} not found")
    if text is not None:
        b.text = text
    if tags is not None:
        b.tags = list(tags)
    if selection_override is not None:
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
            from services.embedding_service import maybe_refresh_profile_embedding

            await maybe_refresh_profile_embedding(session, user_id=prof.user_id)
    return b


async def delete_bullet(session: AsyncSession, bullet_id: int) -> bool:
    b = await get_bullet(session, bullet_id)
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
    bullets = await get_bullets_for_experience(session, experience_id)
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
    return await get_bullets_for_experience(session, experience_id)


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
