"""Alembic 0021 round-trip — auto-apply hardening Settings columns.

Plan 78 (0.4.0.13 + 0.4.0.20). Tests both directions:
- upgrade adds `auto_apply_per_board_daily_caps` JSONB + `auto_apply_dry_run` bool
- downgrade removes them

sqlite-only smoke (table-shape assertion); JSONB compiles to TEXT under
sqlite so the column exists with a TEXT affinity. Postgres-specific JSONB
semantics are exercised in the live-DB suite.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def _load_migration_0021():
    repo_root = Path(__file__).resolve().parent.parent
    path = repo_root / "migrations" / "versions" / "0021_auto_apply_hardening.py"
    spec = importlib.util.spec_from_file_location("_alembic_0021", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_pre_0021_tables(engine: sa.Engine) -> None:
    """Stub the minimal `settings` shape at post-0020."""
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


def test_0021_upgrade_adds_two_auto_apply_hardening_columns(tmp_path):
    db_path = tmp_path / "rt.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0021_tables(engine)
        migration = _load_migration_0021()
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()

        cols = _table_columns(engine, "settings")
        assert "auto_apply_per_board_daily_caps" in cols
        assert "auto_apply_dry_run" in cols
        # Both NOT NULL with safe defaults so existing rows survive.
        assert cols["auto_apply_per_board_daily_caps"]["nullable"] is False
        assert cols["auto_apply_dry_run"]["nullable"] is False
    finally:
        engine.dispose()


def test_0021_downgrade_drops_both_columns(tmp_path):
    db_path = tmp_path / "rt.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0021_tables(engine)
        migration = _load_migration_0021()
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.downgrade()

        cols = _table_columns(engine, "settings")
        assert "auto_apply_per_board_daily_caps" not in cols
        assert "auto_apply_dry_run" not in cols
    finally:
        engine.dispose()


def test_0021_upgrade_default_value_persisted(tmp_path):
    """Existing rows get the `auto_apply_dry_run=false` + `{}` defaults."""
    db_path = tmp_path / "rt.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0021_tables(engine)
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO settings (user_id, llm_provider, created_at, updated_at) "
                    "VALUES (1, 'anthropic', '2026-05-21', '2026-05-21')"
                )
            )

        migration = _load_migration_0021()
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()

        with engine.begin() as conn:
            row = conn.execute(
                sa.text(
                    "SELECT auto_apply_per_board_daily_caps, auto_apply_dry_run "
                    "FROM settings WHERE user_id = 1"
                )
            ).first()
        assert row is not None
        # JSONB compiles to TEXT under sqlite; default surfaces as the literal "{}".
        assert row[0] == "{}"
        # Boolean compiles to INTEGER; server_default 'false' lands as 0.
        assert int(row[1]) == 0
    finally:
        engine.dispose()
