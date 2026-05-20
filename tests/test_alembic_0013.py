"""Alembic 0013 round-trip — JobEmbedding + Settings semantic-match columns.

Plan 61 / 0.2.7.16. Mirrors `tests/test_alembic_0008.py` shape; sqlite cannot
host pgvector's VECTOR(N) type so the migration paths around `is_postgres`
guard the HNSW + column-type rewrite. We assert the table + 4 new Settings
columns appear on sqlite; the HNSW index requires a Postgres + pgvector
target, exercised in the live-DB suite.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def _load_migration_0013():
    repo_root = Path(__file__).resolve().parent.parent
    path = repo_root / "migrations" / "versions" / "0013_job_embedding.py"
    spec = importlib.util.spec_from_file_location("_alembic_0013", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_pre_0013_tables(engine: sa.Engine) -> None:
    """Stub the FK targets + a minimal `settings` row at the post-0011 shape."""
    metadata = sa.MetaData()
    sa.Table("user", metadata, sa.Column("id", sa.Integer, primary_key=True))
    sa.Table("job", metadata, sa.Column("id", sa.Integer, primary_key=True))
    sa.Table(
        "settings",
        metadata,
        sa.Column("user_id", sa.Integer, primary_key=True),
        sa.Column("llm_provider", sa.String(), nullable=False),
        sa.Column(
            "auto_apply_immediate_dispatch", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    metadata.create_all(engine)


def _table_columns(engine: sa.Engine, table: str) -> set[str]:
    inspector = sa.inspect(engine)
    if table not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns(table)}


def test_0013_upgrade_creates_job_embedding_and_settings_cols(tmp_path):
    db_path = tmp_path / "rt.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0013_tables(engine)
        migration = _load_migration_0013()
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()

        je_cols = _table_columns(engine, "job_embedding")
        for required in (
            "job_id",
            "user_id",
            "embedding",
            "model",
            "dim",
            "content_hash",
            "created_at",
            "updated_at",
        ):
            assert required in je_cols, required

        settings_cols = _table_columns(engine, "settings")
        for required in (
            "semantic_match_enabled",
            "embedding_provider",
            "semantic_match_threshold",
            "semantic_match_sync_on_upsert",
        ):
            assert required in settings_cols, required
    finally:
        engine.dispose()


def test_0013_downgrade_drops_job_embedding_and_settings_cols(tmp_path):
    db_path = tmp_path / "rt.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0013_tables(engine)
        migration = _load_migration_0013()
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.downgrade()

        assert "job_embedding" not in sa.inspect(engine).get_table_names()
        settings_cols = _table_columns(engine, "settings")
        for sentinel in (
            "semantic_match_enabled",
            "embedding_provider",
            "semantic_match_threshold",
            "semantic_match_sync_on_upsert",
        ):
            assert sentinel not in settings_cols, sentinel
    finally:
        engine.dispose()


def test_0013_full_round_trip_is_idempotent(tmp_path):
    db_path = tmp_path / "rt.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0013_tables(engine)
        migration = _load_migration_0013()
        for step in ("upgrade", "downgrade", "upgrade"):
            with engine.begin() as conn:
                ctx = MigrationContext.configure(conn)
                with Operations.context(ctx):
                    getattr(migration, step)()
        assert "job_embedding" in sa.inspect(engine).get_table_names()
    finally:
        engine.dispose()
