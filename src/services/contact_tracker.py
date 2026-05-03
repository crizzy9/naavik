"""Contact tracker — CRUD + dedup + state inference from outreach messages.

Per BACKEND.md § H.1 + plan 10 § C (contact_tracker complete). Wave 6 closes
the gap from Wave 4 (which had partial CRUD): adds dedup + state-inference
helpers that roll up to `Application.referral_state` via
`application_service._roll_up_referral_state`.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import (
    Contact,
    ContactApplicationLink,
    ContactType,
    OutreachMessage,
    ReferralState,
)

log = logging.getLogger(__name__)

# Strip placeholder/redacted addresses (per Wave 3 deviation note).
_PLACEHOLDER_EMAIL = re.compile(r"^\[?email[^@]*@[^\]]*\]?$|^placeholder.*", re.IGNORECASE)
_LINKEDIN_HANDLE_RE = re.compile(r"linkedin\.com/in/([^/?#]+)")


def _normalize_email(raw: str | None) -> str | None:
    if not raw:
        return None
    s = raw.strip().lower()
    if not s or _PLACEHOLDER_EMAIL.match(s):
        return None
    return s


def _normalize_linkedin_id(raw: str | None) -> str | None:
    if not raw:
        return None
    m = _LINKEDIN_HANDLE_RE.search(raw)
    if m:
        return m.group(1).lower()
    return raw.strip().lstrip("@").lower() or None


# ── CRUD ───────────────────────────────────────────────────────────────


async def get_contact(session: AsyncSession, contact_id: int) -> Contact | None:
    return (
        await session.exec(
            select(Contact).where(
                Contact.id == contact_id, Contact.deleted_at.is_(None)
            )
        )
    ).one_or_none()


async def find_duplicate(
    session: AsyncSession,
    *,
    user_id: int,
    email: str | None = None,
    linkedin_id: str | None = None,
    name: str | None = None,
    company: str | None = None,
) -> Contact | None:
    """Look for an existing Contact that would conflict with a new entry.

    Match priority (first hit wins):
    1. Same `linkedin_id` for this user.
    2. Same `email` (non-placeholder) for this user.
    3. Same `(user_id, name, company)` heuristic.
    """
    if linkedin_id:
        normalized = _normalize_linkedin_id(linkedin_id)
        if normalized:
            row = (
                await session.exec(
                    select(Contact).where(
                        Contact.user_id == user_id,
                        Contact.linkedin_id == normalized,
                        Contact.deleted_at.is_(None),
                    )
                )
            ).one_or_none()
            if row:
                return row
    norm_email = _normalize_email(email)
    if norm_email:
        row = (
            await session.exec(
                select(Contact).where(
                    Contact.user_id == user_id,
                    Contact.email == norm_email,
                    Contact.deleted_at.is_(None),
                )
            )
        ).one_or_none()
        if row:
            return row
    if name and company:
        row = (
            await session.exec(
                select(Contact).where(
                    Contact.user_id == user_id,
                    Contact.name == name,
                    Contact.company == company,
                    Contact.deleted_at.is_(None),
                )
            )
        ).one_or_none()
        if row:
            return row
    return None


async def upsert_contact(
    session: AsyncSession,
    *,
    user_id: int,
    type: ContactType,
    name: str,
    company: str,
    title: str | None = None,
    linkedin_url: str | None = None,
    linkedin_id: str | None = None,
    email: str | None = None,
    notes: str | None = None,
    relationship: str | None = None,
    source: str | None = None,
) -> tuple[Contact, bool]:
    """Insert or update; returns `(row, created_new)`."""
    norm_email = _normalize_email(email)
    norm_linkedin_id = _normalize_linkedin_id(linkedin_id)
    existing = await find_duplicate(
        session,
        user_id=user_id,
        email=email,
        linkedin_id=linkedin_id or linkedin_url,
        name=name,
        company=company,
    )
    now = datetime.now(UTC)
    if existing is not None:
        # Merge non-conflicting metadata
        if title and not existing.title:
            existing.title = title
        if linkedin_url and not existing.linkedin_url:
            existing.linkedin_url = linkedin_url
        if norm_linkedin_id and not existing.linkedin_id:
            existing.linkedin_id = norm_linkedin_id
        if norm_email and not existing.email:
            existing.email = norm_email
        if notes and not existing.notes:
            existing.notes = notes
        existing.updated_at = now
        session.add(existing)
        await session.flush()
        return existing, False
    contact = Contact(
        user_id=user_id,
        type=type,
        name=name,
        title=title,
        company=company,
        linkedin_url=linkedin_url,
        linkedin_id=norm_linkedin_id,
        email=norm_email,
        notes=notes,
        relationship=relationship,
        source=source,
        created_at=now,
        updated_at=now,
    )
    session.add(contact)
    await session.flush()
    return contact, True


async def soft_delete(session: AsyncSession, contact_id: int) -> Contact | None:
    contact = await get_contact(session, contact_id)
    if contact is None:
        return None
    contact.deleted_at = datetime.now(UTC)
    contact.updated_at = contact.deleted_at
    session.add(contact)
    await session.flush()
    return contact


# ── State inference (roll up to ContactApplicationLink + Application) ──


async def infer_link_referral_state(
    session: AsyncSession, *, link_id: int
) -> ReferralState:
    """Infer `ContactApplicationLink.referral_state` from outreach activity.

    Rules (Phase 1 best-effort; Phase 4 layers in email-classification signals):
    - PROVIDED: any OutreachMessage to the linked contact has
      `intent == REFERRAL_REQUEST` AND `replied_at IS NOT NULL`
      AND response_summary mentions "submitted/forwarded/referred".
    - IN_FLIGHT: REFERRAL_REQUEST sent, replied positively, but no
      "submitted/forwarded" signal yet.
    - REQUESTED: REFERRAL_REQUEST sent, no reply.
    - DECLINED: replied with "decline / no" signal.
    - NONE: no referral-intent outreach.
    """
    link = (
        await session.exec(
            select(ContactApplicationLink).where(
                ContactApplicationLink.id == link_id
            )
        )
    ).one_or_none()
    if link is None:
        return ReferralState.NONE
    msgs = (
        await session.exec(
            select(OutreachMessage).where(
                OutreachMessage.contact_id == link.contact_id,
                OutreachMessage.application_id == link.application_id,
            )
        )
    ).all()
    if not msgs:
        return ReferralState.NONE

    has_referral = any(
        m.intent.value == "referral_request" for m in msgs
    )
    if not has_referral:
        return link.referral_state

    referral_msgs = [m for m in msgs if m.intent.value == "referral_request"]
    replied = [m for m in referral_msgs if m.replied_at is not None]
    if not replied:
        return ReferralState.REQUESTED
    summaries = " ".join((m.response_summary or "").lower() for m in replied)
    if any(kw in summaries for kw in ("submitted", "forwarded", "referred", "passed along")):
        new_state = ReferralState.PROVIDED
    elif any(kw in summaries for kw in ("decline", "no thanks", "not able", "can't help")):
        new_state = ReferralState.DECLINED
    else:
        new_state = ReferralState.IN_FLIGHT

    if link.referral_state != new_state:
        link.referral_state = new_state
        link.updated_at = datetime.now(UTC)
        session.add(link)
        await session.flush()
    return new_state


async def update_link_referral_state(
    session: AsyncSession,
    *,
    link_id: int,
    new_state: ReferralState,
    notes: str | None = None,
) -> ContactApplicationLink | None:
    """Manual user override (e.g. clicking "Mark as referred" in the UI)."""
    link = (
        await session.exec(
            select(ContactApplicationLink).where(
                ContactApplicationLink.id == link_id
            )
        )
    ).one_or_none()
    if link is None:
        return None
    link.referral_state = new_state
    if notes:
        link.notes = notes
    link.updated_at = datetime.now(UTC)
    if new_state in {ReferralState.PROVIDED, ReferralState.IN_FLIGHT}:
        link.introduced_at = link.introduced_at or datetime.now(UTC)
    session.add(link)
    await session.flush()
    return link


# ── Inactivity / silent-contact detection ──────────────────────────────


async def silent_contacts_for_user(
    session: AsyncSession,
    *,
    user_id: int,
    days_silent: int = 14,
) -> list[Contact]:
    """Contacts last touched ≥ N days ago. Powers Tracking · followup pile."""
    threshold = datetime.now(UTC) - timedelta(days=days_silent)
    rows = (
        await session.exec(
            select(Contact).where(
                Contact.user_id == user_id,
                Contact.deleted_at.is_(None),
                Contact.last_touch_at.is_not(None),
                Contact.last_touch_at < threshold,
            )
        )
    ).all()
    return list(rows)
