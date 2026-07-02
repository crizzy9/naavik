"""EmailThread entity — auto-classified email threads anchored to Applications.

Per DATA_MODEL.md § C. Messages stored as JSONB list on the row for Phase 1;
Phase 2+ may promote to a separate `EmailMessage` table.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from ._common import utcnow
from .enums import EmailClassification


class EmailThread(SQLModel, table=True):
    __tablename__ = "email_thread"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "thread_id_external",
            name="uq_email_thread_external",
        ),
        Index(
            "ix_email_thread_user_class_latest",
            "user_id",
            "classification",
            "latest_message_at",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", ondelete="CASCADE", index=True)
    application_id: int | None = Field(
        default=None,
        foreign_key="application.id",
        ondelete="SET NULL",
        index=True,
    )
    contact_id: int | None = Field(
        default=None,
        foreign_key="contact.id",
        ondelete="SET NULL",
        index=True,
    )

    provider: str  # "gmail" | "outlook" | "imap"
    thread_id_external: str
    subject: str
    classification: EmailClassification
    auto_classified: bool = Field(default=True)
    manually_verified: bool = Field(default=False)

    latest_message_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )
    message_count: int = Field(default=0)
    messages: list = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default="[]"),
    )

    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
