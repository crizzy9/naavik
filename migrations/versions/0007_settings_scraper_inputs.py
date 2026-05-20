"""Settings — per-user scraper inputs + consecutive-fail counter (plan 35).

Revision ID: 0007_settings_scraper_inputs
Revises: 0006_job_dedup
Create Date: 2026-05-19

Per docs/plans/35-0.2.0.10-apscheduler.md § D.4 + § D.5. Five additive nullable
columns on `settings` to support the six-per-source cron firing:

- `linkedin_keywords` (ARRAY[String], nullable) — LinkedIn search terms.
- `linkedin_location` (String, nullable) — LinkedIn search location.
- `indeed_keywords` (ARRAY[String], nullable) — Indeed search terms.
- `indeed_location` (String, nullable) — Indeed search location.
- `consecutive_scrape_failures` (JSONB, NOT NULL default '{}') — per-source
  consecutive-FAILED counter; cron auto-skips at 3, resets on first
  SUCCESS / PARTIAL. Key = `JobSource.value`; value = `int`.

Downgrade reverses cleanly. SQLite caveat: ARRAY + JSONB degrade to String;
production runs Postgres.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_settings_scraper_inputs"
down_revision: str | None = "0006_job_dedup"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    array_type = postgresql.ARRAY(sa.String()) if is_postgres else sa.String()
    jsonb_type = postgresql.JSONB if is_postgres else sa.String()

    op.add_column(
        "settings",
        sa.Column("linkedin_keywords", array_type, nullable=True),
    )
    op.add_column(
        "settings",
        sa.Column("linkedin_location", sa.String(), nullable=True),
    )
    op.add_column(
        "settings",
        sa.Column("indeed_keywords", array_type, nullable=True),
    )
    op.add_column(
        "settings",
        sa.Column("indeed_location", sa.String(), nullable=True),
    )
    op.add_column(
        "settings",
        sa.Column(
            "consecutive_scrape_failures",
            jsonb_type,
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("settings", "consecutive_scrape_failures")
    op.drop_column("settings", "indeed_location")
    op.drop_column("settings", "indeed_keywords")
    op.drop_column("settings", "linkedin_location")
    op.drop_column("settings", "linkedin_keywords")
