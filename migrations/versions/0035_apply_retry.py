"""Apply-target retry bookkeeping — no more silent dead ends.

Revision ID: 0035_apply_retry
Revises: 0034_apply_resolved_via
Create Date: 2026-07-03

Resolution used to run exactly once per job: the sweep selects
`apply_kind IS NULL`, so anything stamped "external"/"unknown" with no
apply_url (every pre-two-tier row) stayed a dead end forever.
`apply_resolve_attempts` counts attempts; `apply_next_resolve_at` non-NULL
schedules the next retry (backoff ladder in services/apply_site_resolver).
The backfill marks existing dead ends due-now so the very next sweep routes
them through the two-tier resolver (Tier B included).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035_apply_retry"
down_revision: str | None = "0034_apply_resolved_via"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "job",
        sa.Column("apply_resolve_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "job", sa.Column("apply_next_resolve_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(
        "ix_job_apply_retry_due",
        "job",
        ["apply_next_resolve_at"],
        postgresql_where=sa.text("apply_next_resolve_at IS NOT NULL AND deleted_at IS NULL"),
    )
    # Backfill: rows the old resolver left as dead ends become retry-eligible
    # immediately (attempt 1 already spent by that old run).
    op.execute(
        """
        UPDATE job
        SET apply_resolve_attempts = 1, apply_next_resolve_at = now()
        WHERE apply_kind IN ('external', 'unknown')
          AND apply_url IS NULL
          AND deleted_at IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_job_apply_retry_due", table_name="job")
    op.drop_column("job", "apply_next_resolve_at")
    op.drop_column("job", "apply_resolve_attempts")
