"""Thread-level job link — plan 96 slice 96c1 (R3 entity reachability).

Revision ID: 0046_email_thread_job_link
Revises: 0045_full_body_optin
Create Date: 2026-07-08

- `email_thread.job_id` — nullable FK to `job`, denormalized from the
  linked application (messages reach the job via their thread). Set at
  every thread-link site; also settable for detected-process mail that
  resolves to a library job pre-application. A message-level job_id was
  rejected (two writers for one fact); read-time company-key grouping
  stays for unresolved mail.
- Backfill: threads already linked to an application inherit its job_id.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0046_email_thread_job_link"
down_revision = "0045_full_body_optin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "email_thread",
        sa.Column("job_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_email_thread_job_id",
        "email_thread",
        "job",
        ["job_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_email_thread_job_id", "email_thread", ["job_id"])
    op.execute(
        """
        UPDATE email_thread
        SET job_id = application.job_id
        FROM application
        WHERE email_thread.application_id = application.id
          AND application.job_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_email_thread_job_id", table_name="email_thread")
    op.drop_constraint("fk_email_thread_job_id", "email_thread", type_="foreignkey")
    op.drop_column("email_thread", "job_id")
