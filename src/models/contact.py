"""Contact + ContactApplicationLink + OutreachMessage.

Per DATA_MODEL.md § C. ContactApplicationLink is the source of truth for
per-link `referral_state`; the rolled-up `Application.referral_state` is
computed at the service layer.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Index, UniqueConstraint
from sqlmodel import Field, SQLModel

from ._common import utcnow
from .enums import ContactType, OutreachIntent, OutreachStatus, ReferralState


class Contact(SQLModel, table=True):
    __tablename__ = "contact"
    __table_args__ = (
        Index("ix_contact_user_company", "user_id", "company"),
        Index(
            "ix_contact_user_linkedin_unique",
            "user_id",
            "linkedin_id",
            unique=True,
            postgresql_where="linkedin_id IS NOT NULL AND deleted_at IS NULL",
        ),
        # Email uniqueness is intentionally NOT enforced — Phase 1 fixtures
        # use placeholder/redacted emails ("[email protected]") for
        # LinkedIn-only contacts and real-world recruiter pools. Tighten to
        # `(user_id, email) WHERE email IS NOT NULL` in Phase 2 once we
        # validate inbound emails at the service layer.
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", ondelete="CASCADE", index=True)

    type: ContactType
    name: str
    title: str | None = None
    company: str = Field(index=True)
    linkedin_url: str | None = None
    linkedin_id: str | None = None
    linkedin_degree: str | None = None
    email: str | None = None
    relationship: str | None = None
    source: str | None = None
    notes: str | None = None
    last_touch_at: datetime | None = Field(
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
    deleted_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )


class ContactApplicationLink(SQLModel, table=True):
    __tablename__ = "contact_application_link"
    __table_args__ = (
        UniqueConstraint("application_id", "contact_id", name="uq_contact_application_link"),
    )

    id: int | None = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="application.id", ondelete="CASCADE", index=True)
    contact_id: int = Field(foreign_key="contact.id", ondelete="CASCADE", index=True)

    referral_state: ReferralState = Field(default=ReferralState.NONE)
    introduced_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    notes: str | None = None

    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class OutreachMessage(SQLModel, table=True):
    __tablename__ = "outreach_message"
    __table_args__ = (
        Index(
            "ix_outreach_message_user_contact_sent",
            "user_id",
            "contact_id",
            "sent_at",
        ),
        Index("ix_outreach_message_status", "status"),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", ondelete="CASCADE", index=True)
    contact_id: int = Field(foreign_key="contact.id", ondelete="CASCADE", index=True)
    application_id: int | None = Field(
        default=None,
        foreign_key="application.id",
        ondelete="SET NULL",
        index=True,
    )

    intent: OutreachIntent
    channel: str
    subject: str | None = None
    body: str

    status: OutreachStatus = Field(default=OutreachStatus.DRAFT)
    sent_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    opened_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    replied_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    response_summary: str | None = None

    ai_generated: bool = Field(default=False)
    human_edited: bool = Field(default=False)
    drafted_by_model: str | None = None
    linkedin_message_id: str | None = None

    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    deleted_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
