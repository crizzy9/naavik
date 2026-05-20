"""Tier-3 fuzzy dedup — pg_trgm + Job.duplicate_of_id + GIN trigram index.

Revision ID: 0006_job_dedup
Revises: 0005_job_hardening
Create Date: 2026-05-19

Per docs/plans/34-0.2.0.09-job-dedup.md § D.6 (graduating to
docs/design/JOB_DEDUP.md on archive).

Three additive changes:

1. `CREATE EXTENSION IF NOT EXISTS pg_trgm` — built-in contrib, ships with
   Postgres `postgres:16` image + nixpkgs. Idempotent.
2. `Job.duplicate_of_id` — self-FK, nullable, ON DELETE SET NULL.
   Records the tier-3 canonical Job that this row duplicates.
3. `ix_job_company_trgm` — GIN trigram index on `lower(company)` for the
   candidate-narrowing query in `services/dedup.find_duplicate`. Postgres
   only (sqlite has no pg_trgm).

Downgrade reverses cleanly; pg_trgm extension is intentionally NOT dropped
(other plans may grow trgm indexes against other columns).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_job_dedup"
down_revision: str | None = "0005_job_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.add_column(
        "job",
        sa.Column("duplicate_of_id", sa.Integer(), nullable=True),
    )
    # SQLite's `ALTER TABLE ADD CONSTRAINT` is unsupported (mirrors the
    # plan-27 last_scrape_run_id FK skip); production runs Postgres.
    if is_postgres:
        op.create_foreign_key(
            "fk_job_duplicate_of_id",
            "job",
            "job",
            ["duplicate_of_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(
        "ix_job_duplicate_of_id",
        "job",
        ["duplicate_of_id"],
    )

    if is_postgres:
        op.execute(
            "CREATE INDEX ix_job_company_trgm ON job USING GIN (lower(company) gin_trgm_ops)"
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute("DROP INDEX IF EXISTS ix_job_company_trgm")

    op.drop_index("ix_job_duplicate_of_id", table_name="job")
    if is_postgres:
        op.drop_constraint("fk_job_duplicate_of_id", "job", type_="foreignkey")
    op.drop_column("job", "duplicate_of_id")

    # pg_trgm extension intentionally left in place — orthogonal usages
    # may grow against other tables.
