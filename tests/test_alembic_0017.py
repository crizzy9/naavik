"""Alembic 0017 round-trip — ProfileEmbedding + Settings.score_per_dim_weights.

Plan 65 / 0.3.0. Mirrors `tests/test_alembic_0013.py` shape. sqlite cannot
host pgvector's VECTOR(N) type so the migration paths around `is_postgres`
guard the HNSW + column-type rewrite. We assert the table + new Settings
column appear on sqlite; the HNSW index requires Postgres + pgvector,
exercised in the live-DB suite.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

pytestmark = pytest.mark.uses_sample_data_shims


def _load_migration_0017():
    repo_root = Path(__file__).resolve().parent.parent
    path = repo_root / "migrations" / "versions" / "0017_scorer_settings.py"
    spec = importlib.util.spec_from_file_location("_alembic_0017", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_pre_0017_tables(engine: sa.Engine) -> None:
    """Stub the FK targets + minimal `settings` shape at post-0016."""
    metadata = sa.MetaData()
    sa.Table("user", metadata, sa.Column("id", sa.Integer, primary_key=True))
    sa.Table(
        "settings",
        metadata,
        sa.Column("user_id", sa.Integer, primary_key=True),
        sa.Column("llm_provider", sa.String(), nullable=False),
        sa.Column(
            "auto_apply_adapter_confidence_threshold",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.7"),
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


def test_0017_upgrade_creates_profile_embedding_and_settings_col(tmp_path):
    db_path = tmp_path / "rt.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0017_tables(engine)
        migration = _load_migration_0017()
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()

        pe_cols = _table_columns(engine, "profile_embedding")
        for required in (
            "user_id",
            "embedding",
            "model",
            "dim",
            "content_hash",
            "created_at",
            "updated_at",
        ):
            assert required in pe_cols, required

        settings_cols = _table_columns(engine, "settings")
        assert "score_per_dim_weights" in settings_cols
    finally:
        engine.dispose()


def test_0017_downgrade_drops_profile_embedding_and_settings_col(tmp_path):
    db_path = tmp_path / "rt.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0017_tables(engine)
        migration = _load_migration_0017()
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.downgrade()

        assert "profile_embedding" not in sa.inspect(engine).get_table_names()
        settings_cols = _table_columns(engine, "settings")
        assert "score_per_dim_weights" not in settings_cols
    finally:
        engine.dispose()


def test_0017_full_round_trip_is_idempotent(tmp_path):
    db_path = tmp_path / "rt.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0017_tables(engine)
        migration = _load_migration_0017()
        for step in ("upgrade", "downgrade", "upgrade"):
            with engine.begin() as conn:
                ctx = MigrationContext.configure(conn)
                with Operations.context(ctx):
                    getattr(migration, step)()
        assert "profile_embedding" in sa.inspect(engine).get_table_names()
    finally:
        engine.dispose()
