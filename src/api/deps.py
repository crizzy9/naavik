"""Ownership-guard FastAPI dependencies (plan 91 Phase 1.4).

Centralizes the fetch-then-ownership-check that was hand-rolled ~40× across
route handlers — and *forgotten* on the contacts, bullet-fragment, and outreach
routes, which is what produced the IDOR + unauthenticated-read bugs plan 91
Phase 1 fixes. Expressing the check as a dependency puts it in the route
signature, where it cannot be silently omitted the way an inline `if
row.user_id != uid` can.

`require_authed_session` returns `User | None` — None is the debug fake-session,
which maps to the seeded owner (user 1) via `effective_user_id`. In production
the fake session is rejected, so an unauthenticated caller never reaches these.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from db.session import get_session
from models import Application, Bullet, Contact, User
from services.auth import require_authed_session


def effective_user_id(user: User | None) -> int:
    """Acting user id; the debug fake-session (None) maps to the owner."""
    return user.id if user is not None else 1


async def get_owned_contact(
    contact_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
) -> Contact:
    """Fetch a contact the caller owns, else 404 (same shape as a missing row —
    no cross-user existence oracle)."""
    from services import contact_tracker

    contact = await contact_tracker.get_contact(session, contact_id)
    if contact is None or contact.user_id != effective_user_id(user):
        raise HTTPException(status_code=404, detail="Contact not found")
    return contact


async def get_owned_bullet(
    bullet_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
) -> Bullet:
    """Fetch a bullet the caller owns (bullet → experience → profile → user),
    else 404."""
    from services import profile_service

    uid = effective_user_id(user)
    if not await profile_service.owns_bullet(session, bullet_id=bullet_id, user_id=uid):
        raise HTTPException(status_code=404, detail="Bullet not found")
    bullet = await profile_service.get_bullet(session, bullet_id)
    if bullet is None:
        raise HTTPException(status_code=404, detail="Bullet not found")
    return bullet


async def get_owned_application(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
) -> Application:
    """Fetch an application the caller owns, else 404."""
    from services import application_service

    application = await application_service.get_application(session, application_id)
    if application is None or application.user_id != effective_user_id(user):
        raise HTTPException(status_code=404, detail="Application not found")
    return application
