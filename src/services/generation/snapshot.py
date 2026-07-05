"""Profile snapshot loader + resume-reuse heuristics.

Split out of services/document_generator.py in plan 91 Phase 4.3;
behaviour unchanged. Internal calls to patched seams go through `svc()`
(the facade) so test interception keeps working.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import (
    Application,
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
    Skill,
)
from services.generation.common import _select_template, _template_version

log = logging.getLogger(__name__)


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
      4. the doc was compiled from the current template source (template_version)
    """
    if application.docs_state != DocsState.READY:
        return False
    latest = await _latest_resume(session, application.id)
    if latest is None or not latest.bullet_selection:
        return False
    selected_ids = latest.bullet_selection.get("selected_ids") or []
    if not selected_ids:
        return False
    # Compare template source — docs compiled from an older template must
    # regenerate, never be reused as-is (pre-stamp docs have no version and
    # therefore never qualify).
    template_name, _ = _select_template(application, None)
    if latest.bullet_selection.get("template_version") != _template_version(template_name):
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
