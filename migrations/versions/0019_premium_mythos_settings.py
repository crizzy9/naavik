"""PREMIUM-tier Settings columns — plan 67 (0.3.4) § T11.

Revision ID: 0019_premium_mythos_settings
Revises: 0018_generation_trace_and_settings
Create Date: 2026-05-21

Adds `Settings.generation_tier` (free | premium; default free) +
`Settings.originality_api_key` (nullable; secret material per-user via
Settings DB column per AGENTS.md § Key Conventions § CLI vault-sunset).
Both safe defaults; no backfill required.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_premium_mythos_settings"
down_revision: str | None = "0018_generation_trace_and_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "settings",
        sa.Column(
            "generation_tier",
            sa.String(length=20),
            nullable=False,
            server_default="free",
        ),
    )
    op.add_column(
        "settings",
        sa.Column(
            "originality_api_key",
            sa.String(length=200),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("settings", "originality_api_key")
    op.drop_column("settings", "generation_tier")
