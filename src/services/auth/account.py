"""Account lifecycle service — hard-delete a user and every row they own.

Powers `POST /api/v1/settings/account/delete` (the Settings · Account "Delete
my account" action). Replaces the plan-09 stub that returned 204 without
removing anything (a fake-success state).

Deletion is explicit + FK-safe-ordered rather than relying on database
`ON DELETE CASCADE` alone: it works identically on Postgres (production) and
the in-memory SQLite used by the service-layer test suite (where FK cascade is
off by default). The `0025_fk_ondelete_rules` migration adds the DB-level
cascade as defense-in-depth for any path that deletes a `user` row directly.
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import delete
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from config import settings as app_settings
from models import (
    ApiUsage,
    AppEvent,
    Application,
    ApplicationScreenerAnswer,
    Bullet,
    Certification,
    Contact,
    ContactApplicationLink,
    Education,
    EmailAccount,
    EmailMessage,
    EmailThread,
    Experience,
    GeneratedDocument,
    Job,
    JobEmbedding,
    JobScrapeRun,
    OutreachMessage,
    Profile,
    ProfileAnswer,
    ProfileEmbedding,
    Project,
    RevokedJwt,
    Settings,
    Skill,
    User,
)

log = logging.getLogger(__name__)


async def delete_user_account(session: AsyncSession, *, user_id: int) -> bool:
    """Hard-delete `user_id` and all owned rows. Returns True if the user existed.

    Caller owns the commit (mirrors every other state-changing handler in the
    codebase). Rows are removed child → parent so no FK is ever violated
    mid-transaction regardless of the DB's cascade support.
    """
    user = (await session.exec(select(User).where(User.id == user_id))).one_or_none()
    if user is None:
        return False

    # ── Application-scoped children (resolved via the user's application ids) ──
    app_ids = list(
        (await session.exec(select(Application.id).where(Application.user_id == user_id))).all()
    )
    if app_ids:
        await session.exec(
            delete(GeneratedDocument).where(GeneratedDocument.application_id.in_(app_ids))
        )
        await session.exec(
            delete(ApplicationScreenerAnswer).where(
                ApplicationScreenerAnswer.application_id.in_(app_ids)
            )
        )
        await session.exec(
            delete(ContactApplicationLink).where(ContactApplicationLink.application_id.in_(app_ids))
        )

    # ── Profile-scoped children (resolved via the user's profile ids) ─────────
    profile_ids = list(
        (await session.exec(select(Profile.id).where(Profile.user_id == user_id))).all()
    )
    if profile_ids:
        exp_ids = list(
            (
                await session.exec(
                    select(Experience.id).where(Experience.profile_id.in_(profile_ids))
                )
            ).all()
        )
        if exp_ids:
            await session.exec(delete(Bullet).where(Bullet.experience_id.in_(exp_ids)))
        await session.exec(delete(Experience).where(Experience.profile_id.in_(profile_ids)))
        await session.exec(delete(Skill).where(Skill.profile_id.in_(profile_ids)))
        await session.exec(delete(Education).where(Education.profile_id.in_(profile_ids)))
        await session.exec(delete(Project).where(Project.profile_id.in_(profile_ids)))
        await session.exec(delete(Certification).where(Certification.profile_id.in_(profile_ids)))

    # ── Direct user-scoped rows (order: reference-holders before referents) ───
    for model in (
        OutreachMessage,
        EmailMessage,
        EmailThread,
        EmailAccount,
        AppEvent,
        ApiUsage,
        ProfileAnswer,
        Application,
        JobEmbedding,
        Job,
        JobScrapeRun,
        Contact,
        Profile,
        ProfileEmbedding,
        Settings,
        RevokedJwt,
    ):
        await session.exec(delete(model).where(model.user_id == user_id))

    await session.exec(delete(User).where(User.id == user_id))

    # Best-effort filesystem cleanup: uploaded resumes live under
    # <data_dir>/uploads/<user_id>/. DB deletion is the source of truth; a
    # filesystem failure must not abort the account deletion.
    try:
        upload_dir = Path(app_settings.data_dir) / "uploads" / str(user_id)
        if upload_dir.exists():
            for child in sorted(upload_dir.glob("**/*"), reverse=True):
                child.unlink() if child.is_file() else child.rmdir()
            upload_dir.rmdir()
    except OSError as exc:
        log.warning("account delete: upload dir cleanup failed user=%s: %s", user_id, exc)

    return True
