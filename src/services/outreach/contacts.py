"""Contact tracker — Contact read accessors.

Per BACKEND.md § H.1 + plan 10 § C. Mutations live on the outreach routes /
outreach_service; this module is the read surface (single contact + list
accessors) shared by Discover, Outreach, and Tracking.
"""

from __future__ import annotations

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import Contact, ContactApplicationLink

# ── Read accessors ─────────────────────────────────────────────────────


async def get_contact(session: AsyncSession, contact_id: int) -> Contact | None:
    return (
        await session.exec(
            select(Contact).where(Contact.id == contact_id, Contact.deleted_at.is_(None))
        )
    ).one_or_none()


async def list_contacts(session: AsyncSession, user_id: int) -> list[Contact]:
    """All live contacts for the user."""
    stmt = (
        select(Contact)
        .where(Contact.user_id == user_id, Contact.deleted_at.is_(None))
        .order_by(Contact.created_at.desc())
    )
    rows = (await session.exec(stmt)).all()
    return list(rows)


async def list_contacts_for_company(
    session: AsyncSession,
    *,
    user_id: int,
    company: str,
) -> list[Contact]:
    """Live contacts for a specific company."""
    stmt = (
        select(Contact)
        .where(
            Contact.user_id == user_id,
            Contact.company == company,
            Contact.deleted_at.is_(None),
        )
        .order_by(Contact.created_at.desc())
    )
    rows = (await session.exec(stmt)).all()
    return list(rows)


async def list_contacts_for_application(
    session: AsyncSession, application_id: int
) -> list[Contact]:
    """Live contacts linked to a specific Application via ContactApplicationLink."""
    stmt = (
        select(Contact)
        .join(ContactApplicationLink, ContactApplicationLink.contact_id == Contact.id)
        .where(
            ContactApplicationLink.application_id == application_id,
            Contact.deleted_at.is_(None),
        )
    )
    rows = (await session.exec(stmt)).all()
    return list(rows)
