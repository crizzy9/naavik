"""Calendar-invite ground truth — plan 96 slice 96d.

Revision ID: 0047_email_invite
Revises: 0046_email_thread_job_link
Create Date: 2026-07-08

- `email_invite` — one row per observed (ics_uid, recurrence_id, sequence,
  method) VEVENT parsed from `text/calendar` MIME parts / `.ics` attachments.
  The final invite of a chain is DERIVED (`invites.resolve_final`), never
  stored. Cascade-deleted with the carrying message (which cascades with the
  account) per owner decision #7. `recurrence_id` uses '' for non-recurring
  instances so the chain key is a plain UNIQUE constraint.
- `interview_round.invite_uid` — non-unique link from a round to the calendar
  event that schedules it (one event may carry several interviews — owner
  decision 2026-07-08); reschedules/cancellations of the chain propagate to
  every riding round.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0047_email_invite"
down_revision = "0046_email_thread_job_link"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_invite",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "email_message_id",
            sa.Integer(),
            sa.ForeignKey("email_message.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "application_id",
            sa.Integer(),
            sa.ForeignKey("application.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("ics_uid", sa.String(length=512), nullable=False),
        sa.Column("recurrence_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("method", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="confirmed"),
        sa.Column("summary", sa.String(length=512), nullable=True),
        sa.Column("location", sa.String(length=512), nullable=True),
        sa.Column("organizer_email", sa.String(length=254), nullable=True),
        sa.Column("attendee_emails", JSONB(), nullable=False, server_default="[]"),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tz", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "user_id",
            "ics_uid",
            "recurrence_id",
            "sequence",
            "method",
            name="uq_email_invite_chain_key",
        ),
        sa.CheckConstraint(
            "method IN ('request', 'cancel', 'reply', 'counter', 'publish')",
            name="ck_email_invite_method_vocab",
        ),
        sa.CheckConstraint(
            "status IN ('confirmed', 'tentative', 'cancelled')",
            name="ck_email_invite_status_vocab",
        ),
    )
    op.create_index("ix_email_invite_user_id", "email_invite", ["user_id"])
    op.create_index("ix_email_invite_email_message_id", "email_invite", ["email_message_id"])
    op.create_index("ix_email_invite_application_id", "email_invite", ["application_id"])
    op.create_index("ix_email_invite_user_uid", "email_invite", ["user_id", "ics_uid"])

    op.add_column(
        "interview_round",
        sa.Column("invite_uid", sa.String(length=512), nullable=True),
    )
    op.create_index("ix_interview_round_invite_uid", "interview_round", ["invite_uid"])


def downgrade() -> None:
    op.drop_index("ix_interview_round_invite_uid", table_name="interview_round")
    op.drop_column("interview_round", "invite_uid")
    op.drop_index("ix_email_invite_user_uid", table_name="email_invite")
    op.drop_index("ix_email_invite_application_id", table_name="email_invite")
    op.drop_index("ix_email_invite_email_message_id", table_name="email_invite")
    op.drop_index("ix_email_invite_user_id", table_name="email_invite")
    op.drop_table("email_invite")
