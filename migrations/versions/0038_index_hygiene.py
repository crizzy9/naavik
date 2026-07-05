"""Index hygiene — missing FK indexes, role trgm, dropped duplicates.

Revision ID: 0038_index_hygiene
Revises: 0037_appeventkind_auto_apply_values
Create Date: 2026-07-05

Plan 91 Phase 7.1.

Adds:
- `ix_job_warm_intro_contact_id` / `ix_job_last_scrape_run_id` — FK columns
  with no index; every Contact/JobScrapeRun delete (`ON DELETE SET NULL`)
  seq-scans `job` without them.
- `ix_profile_answer_source_screener_answer_id` — same FK-scan story.
- `ix_contact_user_email` — contact dedup + email-inference lookups filter
  by `(user_id, email)`.
- `ix_job_role_trgm` (Postgres-only) — the title-relevance and dedup paths
  fuzzy-match `lower(role)`; company already has its trgm twin (0006).

Drops (redundant duplicates):
- `ix_job_found_at_desc` — exact duplicate of `ix_job_found_at`; a single
  btree serves both scan directions on one column.
- `ix_job_user_id` / `ix_contact_user_id` / `ix_profile_answer_user_id` —
  left-prefix duplicates of `ix_job_user_queue` / `ix_contact_user_company`
  / `ix_profile_answer_user_last_used`.

NOTE for `--autogenerate` users: the expression indexes
(`ix_job_company_trgm`, `ix_job_role_trgm`, the HNSW pair, the
one-active-per-tenant partial) exist only in migrations — SQLModel can't
express opclass/HNSW indexes, and adding them to `__table_args__` would
break the sqlite `create_all` test substrate. Autogenerate will PROPOSE
dropping them; never accept that hunk.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0038_index_hygiene"
down_revision: str | None = "0037_appeventkind_auto_apply_values"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Missing FK / lookup indexes (portable btree).
    op.create_index("ix_job_warm_intro_contact_id", "job", ["warm_intro_contact_id"])
    op.create_index("ix_job_last_scrape_run_id", "job", ["last_scrape_run_id"])
    op.create_index(
        "ix_profile_answer_source_screener_answer_id",
        "profile_answer",
        ["source_screener_answer_id"],
    )
    op.create_index("ix_contact_user_email", "contact", ["user_id", "email"])

    # Redundant duplicates out.
    op.drop_index("ix_job_found_at_desc", table_name="job")
    op.drop_index("ix_job_user_id", table_name="job")
    op.drop_index("ix_contact_user_id", table_name="contact")
    op.drop_index("ix_profile_answer_user_id", table_name="profile_answer")

    # Postgres-only trigram twin of ix_job_company_trgm (0006).
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_job_role_trgm "
            "ON job USING GIN (lower(role) gin_trgm_ops)"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_job_role_trgm")

    op.create_index("ix_profile_answer_user_id", "profile_answer", ["user_id"])
    op.create_index("ix_contact_user_id", "contact", ["user_id"])
    op.create_index("ix_job_user_id", "job", ["user_id"])
    op.create_index("ix_job_found_at_desc", "job", ["found_at"])

    op.drop_index("ix_contact_user_email", table_name="contact")
    op.drop_index(
        "ix_profile_answer_source_screener_answer_id", table_name="profile_answer"
    )
    op.drop_index("ix_job_last_scrape_run_id", table_name="job")
    op.drop_index("ix_job_warm_intro_contact_id", table_name="job")
