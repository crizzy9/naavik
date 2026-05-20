"""Settings.auto_apply_immediate_dispatch flag.

Revision ID: 0011_settings_auto_apply_immediate
Revises: 0010_revoked_jwt
Create Date: 2026-05-20

Per docs/plans/59-0.2.7.12-auto-apply-immediate.md § D.1. Adds the
boolean `auto_apply_immediate_dispatch` column to `settings` with
`server_default='false'` (preserves current behavior on upgrade).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_settings_auto_apply_immediate"
down_revision: str | None = "0010_revoked_jwt"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "settings",
        sa.Column(
            "auto_apply_immediate_dispatch",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("settings", "auto_apply_immediate_dispatch")
