"""Email service — reads over `EmailThread` for Overview + Tracking surfaces.

Plan 60 / 0.2.7.17 — new module created during the `NAAVIK_PERSISTENCE`
removal. Mirrors the in-memory `get_email_threads`,
`email_threads_for_application`, `email_signal_feed`, `get_email_thread`
accessors that lived in `src/db/sample_data.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import EmailThread
from models.enums import ApplicationStatus, EmailClassification


def link_thread(thread: EmailThread, application) -> None:
    """Set both link facts on a thread (plan 96c1): the application AND the
    denormalized job — messages reach the job via their thread, so every
    link site must write both or the job surface goes blind."""
    thread.application_id = application.id
    if getattr(application, "job_id", None) is not None:
        thread.job_id = application.job_id


def unlink_thread_links(thread: EmailThread) -> None:
    """Clear both link facts — a human unlink says the association is
    wrong, which covers the job as much as the application."""
    thread.application_id = None
    thread.job_id = None


async def list_accounts(session: AsyncSession, user_id: int) -> list:
    """Live (non-deleted) EmailAccount rows for the user.

    Single honest source for "is an inbox connected?" across Tracking,
    Overview, and the email-signals SSE gate (P6.1 — the UI used to
    hardcode a connected-Gmail chip regardless of state).
    """
    from models import EmailAccount

    stmt = (
        select(EmailAccount)
        .where(EmailAccount.user_id == user_id, EmailAccount.deleted_at.is_(None))
        .order_by(EmailAccount.created_at)
    )
    rows = (await session.exec(stmt)).all()
    return list(rows)


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


@dataclass(slots=True)
class PendingSuggestion:
    """One email-status suggestion awaiting the owner's Apply/Dismiss
    (plan 96a / B2 — surfaced on the board strip + card chip, not just
    buried inside the conversation section)."""

    application_id: int
    message_id: int
    company: str
    role: str | None
    current_status: ApplicationStatus
    suggested_status: ApplicationStatus
    subject: str
    suggested_at: datetime | None
    pinned: bool


async def list_pending_suggestions(
    session: AsyncSession, *, user_id: int
) -> list[PendingSuggestion]:
    """Pending email-status suggestions across the user's live applications.

    Pending = `suggested_status` set, neither applied nor dismissed, on an
    alive application. Suggestions the pipeline has since caught up with
    (application already at the suggested status) are skipped — showing
    them would ask the owner to confirm a no-op.
    """
    from models import Application, EmailMessage
    from services.applications.pins import get_status_pin

    rows = (
        await session.exec(
            select(EmailMessage, Application)
            .where(
                EmailMessage.user_id == user_id,
                EmailMessage.application_id == Application.id,
                EmailMessage.suggested_status.is_not(None),
                EmailMessage.suggestion_applied_at.is_(None),
                EmailMessage.suggestion_dismissed_at.is_(None),
                Application.deleted_at.is_(None),
            )
            .order_by(EmailMessage.suggested_at.desc())
        )
    ).all()
    out: list[PendingSuggestion] = []
    for msg, application in rows:
        if msg.suggested_status == application.status:
            continue
        out.append(
            PendingSuggestion(
                application_id=application.id,
                message_id=msg.id,
                company=application.company,
                role=application.role,
                current_status=application.status,
                suggested_status=msg.suggested_status,
                subject=msg.subject,
                suggested_at=msg.suggested_at,
                pinned=get_status_pin(application) is not None,
            )
        )
    return out


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
