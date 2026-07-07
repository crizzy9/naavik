"""Staleness settings — plan 95 slice 95e.

Revision ID: 0044_staleness_settings
Revises: 0043_interview_round
Create Date: 2026-07-07

`settings.staleness_stale_days` (flat 30d threshold, § 3.2) and the opt-in
`settings.auto_close_ghosted_after_days` (NULL = off — nothing ever closes
without a click by default).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0044_staleness_settings"
down_revision = "0043_interview_round"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "settings",
        sa.Column("staleness_stale_days", sa.Integer(), nullable=False, server_default="30"),
    )
    op.add_column(
        "settings",
        sa.Column("auto_close_ghosted_after_days", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("settings", "auto_close_ghosted_after_days")
    op.drop_column("settings", "staleness_stale_days")
