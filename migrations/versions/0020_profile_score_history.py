"""Profile.score_history JSONB column — plan 73 (0.3.2.03).

Revision ID: 0020_profile_score_history
Revises: 0019_premium_mythos_settings
Create Date: 2026-05-21

Per master plan 68 Q3 lock + plan 73 § File-by-file edit (post-designer-pick):
aggregation cron writes per-role-family 30-day score trends to this column.
NOT NULL with server_default '{}' so seeded rows pre-cron get safe defaults.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020_profile_score_history"
down_revision: str | None = "0019_premium_mythos_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "profile",
        sa.Column(
            "score_history",
            postgresql.JSONB(),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("profile", "score_history")
