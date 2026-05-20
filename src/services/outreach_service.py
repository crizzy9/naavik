"""Outreach service — list / create / send OutreachMessage rows.

Plan 60 / 0.2.7.17 — new module created during the `NAAVIK_PERSISTENCE`
removal. Mirrors the in-memory `_append_outreach_message` shim +
`outreach_messages_for_contact` / `outreach_messages_for_application`
accessors that lived in `src/db/sample_data.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import OutreachMessage
from models.enums import OutreachIntent, OutreachStatus


async def list_messages_for_contact(
    session: AsyncSession, contact_id: int
) -> list[OutreachMessage]:
    """All OutreachMessages targeted at a contact, newest first."""
    stmt = (
        select(OutreachMessage)
        .where(
            OutreachMessage.contact_id == contact_id,
            OutreachMessage.deleted_at.is_(None),
        )
        .order_by(OutreachMessage.created_at.desc())
    )
    rows = (await session.exec(stmt)).all()
    return list(rows)


async def list_messages_for_application(
    session: AsyncSession, application_id: int
) -> list[OutreachMessage]:
    """All OutreachMessages tied to an Application, newest first."""
    stmt = (
        select(OutreachMessage)
        .where(
            OutreachMessage.application_id == application_id,
            OutreachMessage.deleted_at.is_(None),
        )
        .order_by(OutreachMessage.created_at.desc())
    )
    rows = (await session.exec(stmt)).all()
    return list(rows)


async def list_all_messages(session: AsyncSession, user_id: int) -> list[OutreachMessage]:
    """All OutreachMessages for the user (unfiltered)."""
    stmt = (
        select(OutreachMessage)
        .where(
            OutreachMessage.user_id == user_id,
            OutreachMessage.deleted_at.is_(None),
        )
        .order_by(OutreachMessage.created_at.desc())
    )
    rows = (await session.exec(stmt)).all()
    return list(rows)


async def get_message(session: AsyncSession, message_id: int) -> OutreachMessage | None:
    stmt = select(OutreachMessage).where(
        OutreachMessage.id == message_id,
        OutreachMessage.deleted_at.is_(None),
    )
    return (await session.exec(stmt)).one_or_none()


async def create_message(
    session: AsyncSession,
    *,
    user_id: int,
    contact_id: int,
    application_id: int | None,
    intent: OutreachIntent,
    body: str,
    status: OutreachStatus = OutreachStatus.DRAFT,
    channel: str = "linkedin_dm",
    ai_generated: bool = True,
    drafted_by_model: str | None = "claude-3.5-sonnet-20250219",
) -> OutreachMessage:
    """Insert a new OutreachMessage row."""
    now = datetime.now(UTC)
    msg = OutreachMessage(
        user_id=user_id,
        contact_id=contact_id,
        application_id=application_id,
        intent=intent,
        channel=channel,
        body=body,
        status=status,
        ai_generated=ai_generated,
        drafted_by_model=drafted_by_model,
        created_at=now,
        updated_at=now,
    )
    session.add(msg)
    await session.flush()
    return msg


async def mark_sent(session: AsyncSession, message_id: int) -> OutreachMessage | None:
    """Transition DRAFT → SENT + stamp sent_at."""
    msg = await get_message(session, message_id)
    if msg is None:
        return None
    now = datetime.now(UTC)
    msg.status = OutreachStatus.SENT
    msg.sent_at = now
    msg.updated_at = now
    session.add(msg)
    await session.flush()
    return msg
