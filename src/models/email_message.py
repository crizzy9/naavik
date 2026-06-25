"""EmailMessage entity — per-message inbox row (plan 90 / 0.5.0.01).

Privacy-first storage shape (plan § A.3.c lock): metadata + 200-char snippet
only. Full body is NOT persisted; re-classification refetches from IMAP if
needed. Full-body opt-in is filed as `0.5.0.05a` follow-up.

Sibling to `EmailThread`. EmailThread's inline `messages: list` JSONB column
remains for backward-compat (read-only legacy); new code writes EmailMessage
rows authoritatively.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Index, UniqueConstraint
from sqlmodel import Field, SQLModel

from ._common import utcnow
from .enums import ApplicationStatus, EmailClassification, UnclassifiedReason


class EmailMessage(SQLModel, table=True):
    __tablename__ = "email_message"
    __table_args__ = (
        UniqueConstraint(
            "thread_id",
            "message_id_external",
            name="uq_email_message_external",
        ),
        Index(
            "ix_email_message_thread_received",
            "thread_id",
            "received_at",
        ),
        Index(
            "ix_email_message_user_class_received",
            "user_id",
            "classification",
            "received_at",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    thread_id: int = Field(foreign_key="email_thread.id", index=True)
    application_id: int | None = Field(
        default=None,
        foreign_key="application.id",
        index=True,
    )
    account_id: int | None = Field(
        default=None,
        foreign_key="email_account.id",
        index=True,
    )

    provider: str
    message_id_external: str
    sender_email: str
    sender_name: str | None = None
    subject: str
    snippet: str = Field(max_length=240)
    received_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )

    classification: EmailClassification | None = None
    auto_classified: bool = Field(default=True)
    classification_model: str | None = None
    classification_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    unclassified_reason: UnclassifiedReason | None = None
    urgency: str | None = None

    suggested_status: ApplicationStatus | None = None
    suggested_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    suggestion_dismissed_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    suggestion_applied_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )

    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
