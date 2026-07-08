"""EmailInvite — structured calendar-invite metadata at rest (plan 96 § 5.4).

One row per (ics_uid, recurrence_id, sequence, method) VEVENT observed in the
owner's mail — the raw supersedence LEDGER, owner-approved 2026-07-08. The
_final_ invite for a chain is DERIVED, never stored
(`services.email.invites.resolve_final`): the max-sequence non-cancelled
REQUEST, unless a CANCEL at ≥ that sequence killed the chain.

Invites are the SCHEDULING axis, not the interview axis (owner decision
2026-07-08, execution session 2): one calendar event may carry several
interviews (Chime's 5-segment onsite rode ONE invite; Headway's 4 interviews
rode THREE). Rounds link to their scheduling container via
`InterviewRound.invite_uid` (non-unique); this table stays 1:1 with observed
VEVENTs.

`method`/`status` are string + CHECK vocabularies (the 0040 pattern);
`recurrence_id` uses '' (not NULL) for non-recurring instances so the chain
key can be a plain UNIQUE constraint.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from ._common import utcnow

INVITE_METHODS = ("request", "cancel", "reply", "counter", "publish")
INVITE_STATUSES = ("confirmed", "tentative", "cancelled")


class EmailInvite(SQLModel, table=True):
    __tablename__ = "email_invite"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "ics_uid",
            "recurrence_id",
            "sequence",
            "method",
            name="uq_email_invite_chain_key",
        ),
        CheckConstraint(
            "method IN ('request', 'cancel', 'reply', 'counter', 'publish')",
            name="ck_email_invite_method_vocab",
        ),
        CheckConstraint(
            "status IN ('confirmed', 'tentative', 'cancelled')",
            name="ck_email_invite_status_vocab",
        ),
        Index("ix_email_invite_user_uid", "user_id", "ics_uid"),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", ondelete="CASCADE", index=True)
    email_message_id: int = Field(
        foreign_key="email_message.id",
        ondelete="CASCADE",
        index=True,
    )
    application_id: int | None = Field(
        default=None,
        foreign_key="application.id",
        ondelete="SET NULL",
        index=True,
    )

    ics_uid: str = Field(max_length=512)
    # '' = not a recurring-event instance (plain UNIQUE beats coalesce()).
    recurrence_id: str = Field(default="", max_length=64)
    sequence: int = Field(default=0)
    method: str = Field(max_length=20)
    status: str = Field(default="confirmed", max_length=20)

    summary: str | None = Field(default=None, max_length=512)
    location: str | None = Field(default=None, max_length=512)
    organizer_email: str | None = Field(default=None, max_length=254)
    attendee_emails: list = Field(default_factory=list, sa_column=Column(JSONB, nullable=False))

    starts_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    ends_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    # Original TZID of DTSTART (times are stored normalized to UTC).
    tz: str | None = Field(default=None, max_length=64)

    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
