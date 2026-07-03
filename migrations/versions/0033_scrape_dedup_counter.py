"""Scrape-run dedup counter — known-ID skip bookkeeping.

Revision ID: 0033_scrape_dedup_counter
Revises: 0032_apply_site
Create Date: 2026-07-03

2026-07 scraping volume rework: aggregator scrapers skip the per-listing
detail fetch for jobs already in the library. `duplicates_skipped` records
how much of each run's budget the skip saved.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033_scrape_dedup_counter"
down_revision: str | None = "0032_apply_site"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "job_scrape_run",
        sa.Column("duplicates_skipped", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("job_scrape_run", "duplicates_skipped")
