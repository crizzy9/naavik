"""Email service — reads over `EmailThread` for Overview + Tracking surfaces.

Plan 60 / 0.2.7.17 — new module created during the `NAAVIK_PERSISTENCE`
removal. Mirrors the in-memory `get_email_threads`,
`email_threads_for_application`, `email_signal_feed`, `get_email_thread`
accessors that lived in `src/db/sample_data.py`.
"""

from __future__ import annotations

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import EmailThread
from models.enums import EmailClassification


async def list_threads(
    session: AsyncSession,
    user_id: int,
    *,
    application_id: int | None = None,
    classification: EmailClassification | None = None,
) -> list[EmailThread]:
    """All EmailThreads for a user, optionally filtered by app or classification."""
    stmt = select(EmailThread).where(EmailThread.user_id == user_id)
    if application_id is not None:
        stmt = stmt.where(EmailThread.application_id == application_id)
    if classification is not None:
        stmt = stmt.where(EmailThread.classification == classification)
    stmt = stmt.order_by(EmailThread.latest_message_at.desc())
    rows = (await session.exec(stmt)).all()
    return list(rows)


async def get_thread(session: AsyncSession, thread_id: int) -> EmailThread | None:
    stmt = select(EmailThread).where(EmailThread.id == thread_id)
    return (await session.exec(stmt)).one_or_none()


async def list_threads_for_application(
    session: AsyncSession, application_id: int
) -> list[EmailThread]:
    """All EmailThreads attached to an Application, newest first."""
    stmt = (
        select(EmailThread)
        .where(EmailThread.application_id == application_id)
        .order_by(EmailThread.latest_message_at.desc())
    )
    rows = (await session.exec(stmt)).all()
    return list(rows)


async def recent_signals(
    session: AsyncSession,
    user_id: int,
    *,
    limit: int = 6,
) -> list[EmailThread]:
    """Most recent email signals — Overview right rail + Tracking integrations."""
    stmt = (
        select(EmailThread)
        .where(EmailThread.user_id == user_id)
        .order_by(EmailThread.latest_message_at.desc())
        .limit(limit)
    )
    rows = (await session.exec(stmt)).all()
    return list(rows)
