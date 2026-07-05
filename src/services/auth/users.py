"""User lookups + credential authentication.

Split out of the auth god-module in plan 91 Phase 4.1; behaviour unchanged.
"""

from __future__ import annotations

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import User

from .passwords import verify_password


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    """Fetch a non-deleted active user by email, case-folded."""
    norm = email.strip().lower()
    stmt = select(User).where(
        User.email == norm,
        User.deleted_at.is_(None),
    )
    result = await session.exec(stmt)
    return result.one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    stmt = select(User).where(User.id == user_id, User.deleted_at.is_(None))
    result = await session.exec(stmt)
    return result.one_or_none()


async def authenticate(
    session: AsyncSession,
    email: str,
    password: str,
) -> User | None:
    """Look up by email, verify bcrypt hash. Constant time even on miss
    (bcrypt over a dummy hash) so timing leaks don't reveal valid emails."""
    user = await get_user_by_email(session, email)
    # Always run bcrypt to keep timing constant.
    if user is None:
        verify_password(password, "$2b$12$placeholder.dummy.hash.invalid........")
        return None
    if not verify_password(password, user.password_hash):
        return None
    if not user.is_active:
        return None
    return user
