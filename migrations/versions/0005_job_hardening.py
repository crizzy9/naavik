"""Job hardening + JobScrapeRun observability — plan 27 (0.2.0.05).

Revision ID: 0005_job_hardening
Revises: 0004_drop_vault_cols
Create Date: 2026-05-19

Per docs/design/JOB_MODEL.md (graduated from docs/plans/27-0.2.0.05-job-models.md).

Hardens the Phase 1 placeholder Job schema into the production form that
all 9 downstream scraper sub-tasks (0.2.0.06–0.2.0.14) hard-depend on:

- Job adds 6 new columns + 2 new indexes (1 partial-unique dedup + 1 FK).
- JobSource ENUM gets 9 per-source values added (existing AUTOMATED + MANUAL
  retained; AUTOMATED rows remap to per-board values; AUTOMATED stays in
  the type definition because Postgres has no `ALTER TYPE ... DROP VALUE`
  before PG16 — cosmetic only, no functional impact, follow-up row filed).
- VisaRestriction is a NEW Postgres ENUM type; Job.visa_restrictions
  promotes from `varchar` to typed enum via add-column + UPDATE-CASE +
  drop-old + rename (CASE catches free-form sponsorship strings).
- RemotePolicy + SeniorityLevel + JobScrapeStatus are NEW ENUM types.
- New `job_scrape_run` table — one row per scraper invocation (per plan
  § D.2). 2 CHECK constraints + 2 composite indexes.

Downgrade reverses cleanly:
- Drop job_scrape_run table.
- Reverse the visa_restrictions enum promotion (restore varchar).
- Drop the new Job columns + indexes.
- Drop the NEW ENUM types. JobSource type keeps the added values; reverse
  remap would be lossy (the destination per-board info is exactly what was
  lost by the AUTOMATED collapse before this migration ran).

Round-trip test: `tests/test_alembic_0005.py` (sqlite-backed, template
matches tests/test_alembic_0004.py).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_job_hardening"
down_revision: str | None = "0004_drop_vault_cols"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# New enum types (Postgres-side ENUMs created by op.execute since
# postgresql.ENUM(create_type=True) couples awkwardly to ALTER TABLE).
#
# Note: Postgres ENUM members are stored by SQLAlchemy as `.name`
# (UPPERCASE) by default — not `.value`. The pre-0005 `jobsource` type
# contains values `AUTOMATED` and `MANUAL`; new per-source values are added
# in the same UPPERCASE form so Python `JobSource.LINKEDIN` (whose name is
# `LINKEDIN`) writes through SQLAlchemy without a `values_callable`
# override.
_NEW_JOBSOURCE_VALUES = (
    "LINKEDIN",
    "WORKDAY",
    "GREENHOUSE",
    "LEVER",
    "ASHBY",
    "INDEED",
    "COMPANY_DIRECT",
    "RSSHUB",
    "N8N_LEGACY",
)


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # ── 1. JobSource enum — add per-source values (Postgres only) ────────
    # Existing values: AUTOMATED, MANUAL. New: 9 per-source values.
    # Postgres requires ALTER TYPE per value; sqlite has no enum types
    # (StrEnum data round-trips as varchar).
    #
    # Postgres also requires the ALTER TYPE to COMMIT before any UPDATE
    # using the new values (`UnsafeNewEnumValueUsage`). Use alembic's
    # autocommit_block() to escape the migration's enclosing transaction
    # for the ALTER TYPE statements.
    if is_postgres:
        with op.get_context().autocommit_block():
            for value in _NEW_JOBSOURCE_VALUES:
                op.execute(f"ALTER TYPE jobsource ADD VALUE IF NOT EXISTS '{value}'")

    # Data migration: remap AUTOMATED rows to per-board source. The
    # ApplicationBoard enum members are byte-for-byte identical to the new
    # JobSource enum members (GREENHOUSE/WORKDAY/LEVER/ASHBY/LINKEDIN/
    # INDEED/COMPANY_DIRECT/MANUAL), so the cast composes. MANUAL stays
    # MANUAL (no remap needed for that path).
    if is_postgres:
        op.execute("UPDATE job SET source = board::text::jobsource WHERE source = 'AUTOMATED'")
    else:
        # sqlite: source is varchar; just rewrite the string.
        op.execute("UPDATE job SET source = board WHERE source = 'AUTOMATED'")

    # ── 2. New ENUM types (Postgres) ─────────────────────────────────────
    # Values match Python enum `.name` (UPPERCASE) to align with SQLAlchemy's
    # default ENUM type binding.
    if is_postgres:
        op.execute(
            "CREATE TYPE visarestriction AS ENUM ("
            "'US_CITIZEN_ONLY', 'GREEN_CARD_REQUIRED', "
            "'SPONSORSHIP_AVAILABLE', 'NOT_MENTIONED')"
        )
        op.execute("CREATE TYPE remotepolicy AS ENUM ('REMOTE', 'HYBRID', 'ONSITE', 'UNKNOWN')")
        op.execute(
            "CREATE TYPE senioritylevel AS ENUM ("
            "'ENTRY', 'MID', 'SENIOR', 'STAFF', 'PRINCIPAL', "
            "'EXEC', 'UNKNOWN')"
        )
        op.execute(
            "CREATE TYPE jobscrapestatus AS ENUM ("
            "'RUNNING', 'SUCCESS', 'PARTIAL', 'FAILED', 'TIMED_OUT')"
        )

    # ── 3. Job.visa_restrictions: varchar → VisaRestriction enum ─────────
    # Multi-step on Postgres (ENUM cast requires UPDATE-USING). On sqlite,
    # just keep the column as varchar (no enum types in sqlite). The
    # CASE input data is lowercase string values (`'sponsorship_available'`,
    # `'us_citizen_only'`) per the pre-0005 free-form contract; the output
    # is UPPERCASE enum members to match SQLAlchemy's `.name` binding.
    if is_postgres:
        op.add_column(
            "job",
            sa.Column(
                "visa_restrictions_new",
                postgresql.ENUM(
                    "US_CITIZEN_ONLY",
                    "GREEN_CARD_REQUIRED",
                    "SPONSORSHIP_AVAILABLE",
                    "NOT_MENTIONED",
                    name="visarestriction",
                    create_type=False,
                ),
                nullable=True,
            ),
        )
        op.execute(
            """
            UPDATE job SET visa_restrictions_new = CASE
              WHEN visa_restrictions IS NULL THEN 'NOT_MENTIONED'::visarestriction
              WHEN lower(trim(visa_restrictions)) = 'us_citizen_only'
                THEN 'US_CITIZEN_ONLY'::visarestriction
              WHEN lower(trim(visa_restrictions)) = 'green_card_required'
                THEN 'GREEN_CARD_REQUIRED'::visarestriction
              WHEN lower(trim(visa_restrictions)) LIKE '%sponsorship%'
                THEN 'SPONSORSHIP_AVAILABLE'::visarestriction
              ELSE 'NOT_MENTIONED'::visarestriction
            END
            """
        )
        op.drop_column("job", "visa_restrictions")
        op.alter_column(
            "job",
            "visa_restrictions_new",
            new_column_name="visa_restrictions",
            nullable=False,
            server_default="NOT_MENTIONED",
        )

    # ── 4. Job additive columns (Postgres + sqlite) ──────────────────────
    op.add_column(
        "job",
        sa.Column("external_id", sa.String(), nullable=True),
    )
    # Back-fill external_id from url (deterministic sha1 prefix) so
    # NOT NULL + UNIQUE can be applied. SQL function approach keeps it
    # one statement.
    if is_postgres:
        # encode/digest functions live in pgcrypto; substr + md5 is a
        # zero-extension alternative that produces a deterministic hex.
        # 12-char prefix matches the sample_data convention.
        op.execute("UPDATE job SET external_id = substr(md5(url), 1, 12) WHERE external_id IS NULL")
    else:
        # sqlite: md5 isn't built in; use hex(randomblob(6)) which is
        # unique per row (deterministic-from-url isn't reachable in pure
        # sqlite without a function — round-trip test exercises both
        # add-column + uniqueness, not the back-fill semantics).
        op.execute(
            "UPDATE job SET external_id = lower(hex(randomblob(6))) WHERE external_id IS NULL"
        )
    # sqlite's `ALTER TABLE ALTER COLUMN` is unsupported pre-3.35; alembic's
    # batch_alter_table emulates via copy-rebuild. Skip the strict NOT NULL
    # enforcement on sqlite (round-trip test still verifies the column
    # exists + the partial-unique index lands). On Postgres the column
    # flips to NOT NULL cleanly after back-fill.
    if is_postgres:
        op.alter_column("job", "external_id", nullable=False)

    op.add_column(
        "job",
        sa.Column(
            "remote_policy",
            postgresql.ENUM(
                "REMOTE",
                "HYBRID",
                "ONSITE",
                "UNKNOWN",
                name="remotepolicy",
                create_type=False,
            )
            if is_postgres
            else sa.String(),
            nullable=False,
            server_default="UNKNOWN",
        ),
    )
    op.add_column(
        "job",
        sa.Column(
            "seniority_level",
            postgresql.ENUM(
                "ENTRY",
                "MID",
                "SENIOR",
                "STAFF",
                "PRINCIPAL",
                "EXEC",
                "UNKNOWN",
                name="senioritylevel",
                create_type=False,
            )
            if is_postgres
            else sa.String(),
            nullable=True,
        ),
    )
    op.add_column(
        "job",
        sa.Column("posted_at_text", sa.String(), nullable=True),
    )
    op.add_column(
        "job",
        sa.Column(
            "description_extracted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "job",
        sa.Column("description_extraction_model", sa.String(), nullable=True),
    )
    op.add_column(
        "job",
        sa.Column("last_scrape_run_id", sa.Integer(), nullable=True),
    )

    # ── 5. job_scrape_run table (parent for last_scrape_run_id FK) ───────
    op.create_table(
        "job_scrape_run",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("user.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "source",
            postgresql.ENUM(
                "AUTOMATED",
                "MANUAL",
                *_NEW_JOBSOURCE_VALUES,
                name="jobsource",
                create_type=False,
            )
            if is_postgres
            else sa.String(),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "RUNNING",
                "SUCCESS",
                "PARTIAL",
                "FAILED",
                "TIMED_OUT",
                name="jobscrapestatus",
                create_type=False,
            )
            if is_postgres
            else sa.String(),
            nullable=False,
        ),
        sa.Column("triggered_by", sa.String(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "finished_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("requests_made", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("listings_returned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_jobs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_jobs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "errors",
            postgresql.ARRAY(sa.String()) if is_postgres else sa.String(),
            nullable=False,
            server_default="{}" if is_postgres else "[]",
        ),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "raw_meta",
            postgresql.JSONB if is_postgres else sa.String(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name="ck_job_scrape_run_finish_after_start",
        ),
        sa.CheckConstraint(
            "requests_made >= 0 AND listings_returned >= 0 AND new_jobs >= 0 AND updated_jobs >= 0",
            name="ck_job_scrape_run_counters_nonneg",
        ),
    )
    op.create_index(
        "ix_job_scrape_run_source_started",
        "job_scrape_run",
        ["source", "started_at"],
    )
    op.create_index(
        "ix_job_scrape_run_user_status_started",
        "job_scrape_run",
        ["user_id", "status", "started_at"],
    )
    op.create_index(
        "ix_job_scrape_run_started_at",
        "job_scrape_run",
        ["started_at"],
    )

    # ── 6. Job.last_scrape_run_id FK (after target table exists) ─────────
    # Postgres-only — sqlite needs batch_alter_table copy-rebuild for
    # ALTER TABLE ADD CONSTRAINT; the test exercises the column + index
    # surface without it. Production uses Postgres.
    if is_postgres:
        op.create_foreign_key(
            "fk_job_last_scrape_run_id",
            "job",
            "job_scrape_run",
            ["last_scrape_run_id"],
            ["id"],
        )

    # ── 7. Primary dedup index on Job ────────────────────────────────────
    if is_postgres:
        op.create_index(
            "ix_job_user_source_external_id_unique_alive",
            "job",
            ["user_id", "source", "external_id"],
            unique=True,
            postgresql_where=sa.text("deleted_at IS NULL"),
        )
    else:
        # sqlite supports partial indexes via the same syntax.
        op.create_index(
            "ix_job_user_source_external_id_unique_alive",
            "job",
            ["user_id", "source", "external_id"],
            unique=True,
            sqlite_where=sa.text("deleted_at IS NULL"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # Reverse order of upgrade() steps.

    # 7. Drop primary dedup index.
    op.drop_index("ix_job_user_source_external_id_unique_alive", "job")

    # 6. Drop the FK before either side disappears (Postgres only — see
    # upgrade() comment about sqlite batch_alter_table).
    if is_postgres:
        op.drop_constraint("fk_job_last_scrape_run_id", "job", type_="foreignkey")

    # 5. Drop job_scrape_run table + its indexes.
    op.drop_index("ix_job_scrape_run_started_at", "job_scrape_run")
    op.drop_index("ix_job_scrape_run_user_status_started", "job_scrape_run")
    op.drop_index("ix_job_scrape_run_source_started", "job_scrape_run")
    op.drop_table("job_scrape_run")

    # 4. Drop new Job columns.
    op.drop_column("job", "last_scrape_run_id")
    op.drop_column("job", "description_extraction_model")
    op.drop_column("job", "description_extracted_at")
    op.drop_column("job", "posted_at_text")
    op.drop_column("job", "seniority_level")
    op.drop_column("job", "remote_policy")
    op.drop_column("job", "external_id")

    # 3. Reverse visa_restrictions enum promotion (Postgres only;
    # sqlite never promoted).
    if is_postgres:
        op.add_column(
            "job",
            sa.Column("visa_restrictions_old", sa.String(), nullable=True),
        )
        op.execute("UPDATE job SET visa_restrictions_old = visa_restrictions::text")
        op.drop_column("job", "visa_restrictions")
        op.alter_column(
            "job",
            "visa_restrictions_old",
            new_column_name="visa_restrictions",
        )

    # 2. Drop new ENUM types (Postgres only).
    if is_postgres:
        op.execute("DROP TYPE IF EXISTS jobscrapestatus")
        op.execute("DROP TYPE IF EXISTS senioritylevel")
        op.execute("DROP TYPE IF EXISTS remotepolicy")
        op.execute("DROP TYPE IF EXISTS visarestriction")

    # 1. JobSource enum: cannot drop the per-source values cleanly on
    # Postgres before PG16. Leave them in the type definition (the
    # restored AUTOMATED-collapsed path is not reachable post-downgrade
    # because the model code has already changed — operators would need
    # to restore both code + DB to actually revert).
