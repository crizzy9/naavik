"""Alembic 0005 round-trip test — Job hardening + JobScrapeRun.

Plan 27 (0.2.0.05) § D.12: verify the migration is reversible. Builds a
minimal pre-0005 `job` table on a transient SQLite DB and exercises 0005's
`upgrade()` + `downgrade()` directly.

SQLite caveats vs Postgres (intentional asymmetry per migration body):
- SQLite has no ENUM types; `source` and `visa_restrictions` columns stay
  varchar through the migration. The Postgres ENUM-add + UPDATE-USING-CAST
  branches are skipped at runtime. The structural assertions (columns
  added, table created, FK + indexes present) still exercise the additive
  half of the schema work.
- SQLite supports `ALTER TABLE ADD COLUMN` natively (3.25+); the multi-step
  add+rename pattern on Postgres reduces to a no-op on sqlite (column
  visa_restrictions stays varchar — round-trip preserves type).

The 6 new Job columns under test (additive):
- `external_id` (str, NOT NULL after back-fill, UNIQUE per partial idx)
- `remote_policy` (str/enum, NOT NULL, default 'unknown')
- `seniority_level` (str/enum, nullable)
- `posted_at_text` (str, nullable)
- `description_extracted_at` (datetime, nullable)
- `description_extraction_model` (str, nullable)
- `last_scrape_run_id` (int, nullable, FK)

The new table under test:
- `job_scrape_run` with 16 columns + 2 CHECK constraints + 3 indexes.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

_NEW_JOB_COLUMNS = (
    "external_id",
    "remote_policy",
    "seniority_level",
    "posted_at_text",
    "description_extracted_at",
    "description_extraction_model",
    "last_scrape_run_id",
)


def _load_migration_0005():
    """Import the 0005 migration module from disk by path.

    Mirror of tests/test_alembic_0004.py: alembic migrations aren't a
    Python package; direct-file load keeps the test scoped + avoids the
    full env.py boot that pulls pgvector.
    """
    repo_root = Path(__file__).resolve().parent.parent
    path = repo_root / "migrations" / "versions" / "0005_job_hardening.py"
    spec = importlib.util.spec_from_file_location("_alembic_0005", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_pre_0005_job_table(engine: sa.Engine) -> None:
    """Stand up a `job` + `user` table at the Wave-4 (pre-plan-27) shape.

    Plenty of columns omitted — only those the migration reads/touches +
    a handful of innocuous ones to verify nothing else is mutated.
    """
    metadata = sa.MetaData()
    sa.Table(
        "user",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(), nullable=False),
    )
    sa.Table(
        "job",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("user.id"), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("board", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("url_type", sa.String(), nullable=False),
        sa.Column("company", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("visa_restrictions", sa.String(), nullable=True),
        sa.Column("score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("queue_state", sa.String(), nullable=False),
        sa.Column("found_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    metadata.create_all(engine)


def _job_columns(engine: sa.Engine) -> set[str]:
    inspector = sa.inspect(engine)
    return {col["name"] for col in inspector.get_columns("job")}


def _tables(engine: sa.Engine) -> set[str]:
    inspector = sa.inspect(engine)
    return set(inspector.get_table_names())


def _indexes(engine: sa.Engine, table: str) -> set[str]:
    inspector = sa.inspect(engine)
    return {idx["name"] for idx in inspector.get_indexes(table)}


def test_0005_upgrade_adds_job_columns_and_scrape_run_table(tmp_path):
    db_path = tmp_path / "round_trip.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0005_job_table(engine)
        pre_cols = _job_columns(engine)
        for col in _NEW_JOB_COLUMNS:
            assert col not in pre_cols, f"precondition: {col!r} should not exist pre-upgrade"
        assert "job_scrape_run" not in _tables(engine)

        migration = _load_migration_0005()
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()

        post_cols = _job_columns(engine)
        for col in _NEW_JOB_COLUMNS:
            assert col in post_cols, f"{col!r} should exist after upgrade"
        # Existing innocuous columns survive.
        assert "id" in post_cols
        assert "user_id" in post_cols
        assert "url" in post_cols
        # job_scrape_run table created.
        assert "job_scrape_run" in _tables(engine)
        # Primary dedup index present.
        assert "ix_job_user_source_external_id_unique_alive" in _indexes(engine, "job")
        # JobScrapeRun composite indexes present.
        scrape_indexes = _indexes(engine, "job_scrape_run")
        assert "ix_job_scrape_run_source_started" in scrape_indexes
        assert "ix_job_scrape_run_user_status_started" in scrape_indexes
    finally:
        engine.dispose()


def test_0005_downgrade_restores_pre_upgrade_shape(tmp_path):
    db_path = tmp_path / "round_trip.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0005_job_table(engine)
        migration = _load_migration_0005()

        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.downgrade()

        post_cols = _job_columns(engine)
        for col in _NEW_JOB_COLUMNS:
            assert col not in post_cols, f"{col!r} should be gone after downgrade"
        assert "job_scrape_run" not in _tables(engine)
        # Original `job` shape preserved.
        assert "id" in post_cols
        assert "user_id" in post_cols
        assert "url" in post_cols
        assert "visa_restrictions" in post_cols
    finally:
        engine.dispose()


def test_0005_full_round_trip_is_idempotent(tmp_path):
    db_path = tmp_path / "round_trip.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0005_job_table(engine)
        migration = _load_migration_0005()

        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.downgrade()
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()

        post_cols = _job_columns(engine)
        for col in _NEW_JOB_COLUMNS:
            assert col in post_cols, f"{col!r} should be present after upgrade→downgrade→upgrade"
        assert "job_scrape_run" in _tables(engine)
    finally:
        engine.dispose()
