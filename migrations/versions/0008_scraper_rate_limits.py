"""Settings — per-source scraper rate-limit overrides (plan 38).

Revision ID: 0008_scraper_rate_limits
Revises: 0007_settings_scraper_inputs
Create Date: 2026-05-19

Per docs/plans/38-0.2.0.13-rate-limiting-anti-detection.md § D.1. Single
JSONB column on `settings` keyed by `JobSource.value`; nested per-source
dict shape: `{"linkedin": {"rpm": 0.4, "delay_lo": 3.0, "delay_hi": 7.0}}`.

Empty `{}` default falls through to the class-attr fallback table in
`src/scraper/rate_limit.py:_CLASS_ATTR_FALLBACK`. New sources add a key
without a follow-up migration.

Downgrade reverses cleanly. SQLite caveat: JSONB degrades to String;
production runs Postgres.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_scraper_rate_limits"
down_revision: str | None = "0007_settings_scraper_inputs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    jsonb_type = postgresql.JSONB if is_postgres else sa.String()

    op.add_column(
        "settings",
        sa.Column(
            "scraper_rate_limits",
            jsonb_type,
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("settings", "scraper_rate_limits")
