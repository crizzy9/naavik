"""User reads — minimal accessor used by Settings + Account surfaces.

Plan 60 / 0.2.7.17 — added during the `NAAVIK_PERSISTENCE` removal so the
route layer has a service-layer entry point for the User singleton (the
auth path already owns mutation via `services/auth.py`; this module owns
read).
"""

from __future__ import annotations

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import User


async def get_user(session: AsyncSession, user_id: int) -> User | None:
    """Soft-delete-aware single-user fetch."""
    stmt = select(User).where(User.id == user_id, User.deleted_at.is_(None))
    return (await session.exec(stmt)).one_or_none()
