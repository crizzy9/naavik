"""Calendar via secret ICS URL — CalendarConnection + CalendarEvent.

Revision ID: 0030_calendar_events
Revises: 0029_project_kind
Create Date: 2026-07-02

Read-only Google Calendar integration (item 11): the user pastes the
calendar's secret ICS address, stored Fernet-encrypted; a 45-minute cron
syncs a bounded window of events which fuzzy-match to applications.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030_calendar_events"
down_revision: str | None = "0029_project_kind"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "calendar_connection",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
            index=True,
        ),
        sa.Column("label", sa.String(length=120), nullable=False, server_default="Google Calendar"),
        sa.Column("ics_url_encrypted", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ok"),
        sa.Column("last_error", sa.String(length=300), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("event_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "calendar_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "connection_id",
            sa.Integer(),
            sa.ForeignKey("calendar_connection.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("uid", sa.String(length=512), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("location", sa.String(length=512), nullable=True),
        sa.Column("description_snippet", sa.String(length=240), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("all_day", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "matched_application_id",
            sa.Integer(),
            sa.ForeignKey("application.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "uid", name="uq_calendar_event_user_uid"),
    )


def downgrade() -> None:
    op.drop_table("calendar_event")
    op.drop_table("calendar_connection")
