"""Apply-site resolution — where the application ACTUALLY happens.

Revision ID: 0032_apply_site
Revises: 0031_email_inference
Create Date: 2026-07-03

Aggregator listings (LinkedIn/Indeed) usually hand off to an external ATS.
`job.apply_url` + `job.apply_kind` record the resolved application target
(greenhouse / lever / ashby / workday / easy_apply / company_site / ...);
NULL apply_kind = not resolved yet. `apply_resolved_at` stamps the attempt.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032_apply_site"
down_revision: str | None = "0031_email_inference"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("job", sa.Column("apply_url", sa.String(), nullable=True))
    op.add_column("job", sa.Column("apply_kind", sa.String(length=20), nullable=True))
    op.add_column("job", sa.Column("apply_resolved_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "ix_job_apply_kind_pending",
        "job",
        ["id"],
        postgresql_where=sa.text("apply_kind IS NULL AND deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_job_apply_kind_pending", table_name="job")
    op.drop_column("job", "apply_resolved_at")
    op.drop_column("job", "apply_kind")
    op.drop_column("job", "apply_url")
