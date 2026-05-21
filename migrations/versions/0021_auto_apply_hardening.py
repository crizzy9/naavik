"""Auto-apply hardening — plan 78 (0.4.0.13 + 0.4.0.20).

Revision ID: 0021_auto_apply_hardening
Revises: 0020_profile_score_history
Create Date: 2026-05-21

Adds two `settings` columns:
- `auto_apply_per_board_daily_caps` JSONB NOT NULL DEFAULT '{}'  (plan 78 § D.3)
- `auto_apply_dry_run` BOOLEAN NOT NULL DEFAULT FALSE             (plan 78 § D.5)

Additive — reversible via column drops. No data backfill required; defaults
land on existing rows automatically. SQLite caveat: JSONB degrades to String;
production runs Postgres (mirrors the plan-38 / 0008 pattern).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021_auto_apply_hardening"
down_revision: str | None = "0020_profile_score_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    jsonb_type: object = postgresql.JSONB() if is_postgres else sa.String()

    op.add_column(
        "settings",
        sa.Column(
            "auto_apply_per_board_daily_caps",
            jsonb_type,
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column(
        "settings",
        sa.Column(
            "auto_apply_dry_run",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("settings", "auto_apply_dry_run")
    op.drop_column("settings", "auto_apply_per_board_daily_caps")
