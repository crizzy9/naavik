"""Alembic 0019 round-trip — Settings.generation_tier + Settings.originality_api_key.

Plan 67 / 0.3.4 § T11 / T16. Tests both directions:
- upgrade adds the 2 columns with safe defaults
- downgrade removes them

sqlite-only smoke (table-shape assertion); Postgres-specific behavior is
exercised in the live-DB suite.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def _load_migration_0019():
    repo_root = Path(__file__).resolve().parent.parent
    path = repo_root / "migrations" / "versions" / "0019_premium_mythos_settings.py"
    spec = importlib.util.spec_from_file_location("_alembic_0019", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_pre_0019_tables(engine: sa.Engine) -> None:
    """Stub the minimal `settings` shape at post-0018."""
    metadata = sa.MetaData()
    sa.Table("user", metadata, sa.Column("id", sa.Integer, primary_key=True))
    sa.Table(
        "settings",
        metadata,
        sa.Column("user_id", sa.Integer, primary_key=True),
        sa.Column("llm_provider", sa.String(), nullable=False, server_default="anthropic"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    metadata.create_all(engine)


def _table_columns(engine: sa.Engine, table: str) -> dict[str, dict]:
    inspector = sa.inspect(engine)
    if table not in inspector.get_table_names():
        return {}
    return {col["name"]: col for col in inspector.get_columns(table)}


def test_0019_upgrade_adds_two_premium_settings_columns(tmp_path):
    db_path = tmp_path / "rt.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0019_tables(engine)
        migration = _load_migration_0019()
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()

        cols = _table_columns(engine, "settings")
        assert "generation_tier" in cols
        assert "originality_api_key" in cols
        # generation_tier is NOT NULL with default "free"; originality nullable.
        assert cols["generation_tier"]["nullable"] is False
        assert cols["originality_api_key"]["nullable"] is True
    finally:
        engine.dispose()


def test_0019_downgrade_drops_both_columns(tmp_path):
    db_path = tmp_path / "rt.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0019_tables(engine)
        migration = _load_migration_0019()
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.downgrade()

        cols = _table_columns(engine, "settings")
        assert "generation_tier" not in cols
        assert "originality_api_key" not in cols
    finally:
        engine.dispose()


def test_0019_upgrade_default_value_persisted(tmp_path):
    """Existing rows get the `generation_tier='free'` default on upgrade."""
    db_path = tmp_path / "rt.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0019_tables(engine)
        # Insert a pre-existing settings row
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO settings (user_id, llm_provider, created_at, updated_at) "
                    "VALUES (1, 'anthropic', '2026-05-21', '2026-05-21')"
                )
            )

        migration = _load_migration_0019()
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()

        with engine.begin() as conn:
            row = conn.execute(
                sa.text(
                    "SELECT generation_tier, originality_api_key FROM settings WHERE user_id = 1"
                )
            ).first()
        assert row is not None
        assert row[0] == "free"
        assert row[1] is None
    finally:
        engine.dispose()
