"""Interview rounds — plan 95 slice 95d.

Revision ID: 0043_interview_round
Revises: 0042_tracking_v2_corrections
Create Date: 2026-07-07

`interview_round`: rounds within a pipeline stage (§ 3.1). `kind` is a
string + CHECK vocabulary (extensible via two-line migrations, per the 0040
pattern); `sessions` JSONB holds clubbed-onsite sub-sessions.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0043_interview_round"
down_revision = "0042_tracking_v2_corrections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "interview_round",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "application_id",
            sa.Integer(),
            sa.ForeignKey("application.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("round_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("state", sa.String(length=20), nullable=False, server_default="planned"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sessions", JSONB(), nullable=False, server_default="[]"),
        sa.Column("outcome", sa.String(length=20), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="manual"),
        sa.Column(
            "email_message_id",
            sa.Integer(),
            sa.ForeignKey("email_message.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "calendar_event_id",
            sa.Integer(),
            sa.ForeignKey("calendar_event.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("notes", sa.String(length=2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('recruiter_screen', 'technical_screen', 'take_home', "
            "'system_design', 'hiring_manager', 'builder_interview', "
            "'team_match', 'panel', 'onsite_loop', 'other')",
            name="ck_interview_round_kind_vocab",
        ),
        sa.CheckConstraint(
            "state IN ('planned', 'scheduled', 'completed', 'cancelled')",
            name="ck_interview_round_state_vocab",
        ),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN ('passed', 'failed', 'pending')",
            name="ck_interview_round_outcome_vocab",
        ),
        sa.CheckConstraint(
            "source IN ('email', 'calendar', 'notes', 'manual')",
            name="ck_interview_round_source_vocab",
        ),
    )
    op.create_index(
        "ix_interview_round_application_no",
        "interview_round",
        ["application_id", "round_no"],
    )
    op.add_column(
        "email_message",
        sa.Column("extracted_round_kind", sa.String(length=30), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("email_message", "extracted_round_kind")
    op.drop_index("ix_interview_round_application_no", table_name="interview_round")
    op.drop_table("interview_round")
