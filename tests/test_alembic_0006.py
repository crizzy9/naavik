"""Alembic 0006 round-trip — Job.duplicate_of_id + GIN trigram + pg_trgm.

Plan 34 (0.2.0.09) tier-3 fuzzy dedup. Verifies the migration is reversible.
Mirrors the structure of `tests/test_alembic_0005.py`.

SQLite caveats (intentional asymmetry — production runs Postgres):
- `CREATE EXTENSION pg_trgm` is Postgres-only; the migration's `is_postgres`
  branch skips it on sqlite.
- The GIN trigram expression-index `ix_job_company_trgm` is Postgres-only.
- The Job.duplicate_of_id additive column + FK + btree index are exercised
  on sqlite.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def _load_migration_0006():
    repo_root = Path(__file__).resolve().parent.parent
    path = repo_root / "migrations" / "versions" / "0006_job_dedup.py"
    spec = importlib.util.spec_from_file_location("_alembic_0006", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_pre_0006_job_table(engine: sa.Engine) -> None:
    """Stand up a `job` + `user` table at the post-0005 shape, minus the
    new column. Only the columns the migration touches are present.
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
        sa.Column("external_id", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("url_type", sa.String(), nullable=False),
        sa.Column("company", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
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


def _indexes(engine: sa.Engine, table: str) -> set[str]:
    inspector = sa.inspect(engine)
    return {idx["name"] for idx in inspector.get_indexes(table)}


def test_0006_upgrade_adds_duplicate_of_id_and_index(tmp_path):
    db_path = tmp_path / "round_trip.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0006_job_table(engine)
        assert "duplicate_of_id" not in _job_columns(engine)

        migration = _load_migration_0006()
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()

        assert "duplicate_of_id" in _job_columns(engine)
        assert "ix_job_duplicate_of_id" in _indexes(engine, "job")
    finally:
        engine.dispose()


def test_0006_downgrade_drops_column_and_index(tmp_path):
    db_path = tmp_path / "round_trip.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0006_job_table(engine)
        migration = _load_migration_0006()

        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.downgrade()

        assert "duplicate_of_id" not in _job_columns(engine)
        assert "ix_job_duplicate_of_id" not in _indexes(engine, "job")
    finally:
        engine.dispose()


def test_0006_full_round_trip_is_idempotent(tmp_path):
    db_path = tmp_path / "round_trip.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0006_job_table(engine)
        migration = _load_migration_0006()

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

        assert "duplicate_of_id" in _job_columns(engine)
        assert "ix_job_duplicate_of_id" in _indexes(engine, "job")
    finally:
        engine.dispose()
