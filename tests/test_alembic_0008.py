"""Alembic 0008 round-trip — Settings scraper rate-limit overrides.

Plan 38 (0.2.0.13). Mirrors `tests/test_alembic_0007.py`. Single nullable
JSONB column added with default `{}`.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def _load_migration_0008():
    repo_root = Path(__file__).resolve().parent.parent
    path = repo_root / "migrations" / "versions" / "0008_scraper_rate_limits.py"
    spec = importlib.util.spec_from_file_location("_alembic_0008", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_pre_0008_settings_table(engine: sa.Engine) -> None:
    """Stand up `settings` at the post-0007 shape minus `scraper_rate_limits`."""
    metadata = sa.MetaData()
    sa.Table(
        "settings",
        metadata,
        sa.Column("user_id", sa.Integer, primary_key=True),
        sa.Column("llm_provider", sa.String(), nullable=False),
        sa.Column("workday_companies", sa.String(), nullable=False, server_default="{}"),
        sa.Column("sources_enabled", sa.String(), nullable=False, server_default="{}"),
        sa.Column("source_schedules", sa.String(), nullable=False, server_default="{}"),
        sa.Column(
            "consecutive_scrape_failures",
            sa.String(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    metadata.create_all(engine)


def _settings_columns(engine: sa.Engine) -> set[str]:
    inspector = sa.inspect(engine)
    return {col["name"] for col in inspector.get_columns("settings")}


def test_0008_upgrade_adds_scraper_rate_limits_column(tmp_path):
    db_path = tmp_path / "round_trip.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0008_settings_table(engine)
        before = _settings_columns(engine)
        assert "scraper_rate_limits" not in before

        migration = _load_migration_0008()
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()

        after = _settings_columns(engine)
        assert "scraper_rate_limits" in after
    finally:
        engine.dispose()


def test_0008_downgrade_drops_scraper_rate_limits_column(tmp_path):
    db_path = tmp_path / "round_trip.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0008_settings_table(engine)
        migration = _load_migration_0008()

        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.downgrade()

        after = _settings_columns(engine)
        assert "scraper_rate_limits" not in after
    finally:
        engine.dispose()


def test_0008_full_round_trip_is_idempotent(tmp_path):
    db_path = tmp_path / "round_trip.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0008_settings_table(engine)
        migration = _load_migration_0008()

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

        after = _settings_columns(engine)
        assert "scraper_rate_limits" in after
    finally:
        engine.dispose()


def test_0008_default_value_is_empty_dict_string(tmp_path):
    """server_default '{}' lets pre-existing rows fall through to the resolver fallback."""
    db_path = tmp_path / "default.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0008_settings_table(engine)
        migration = _load_migration_0008()
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()

        inspector = sa.inspect(engine)
        cols = {col["name"]: col for col in inspector.get_columns("settings")}
        assert "scraper_rate_limits" in cols
        # SQLite preserves the literal "{}" server default.
        default = cols["scraper_rate_limits"].get("default")
        assert default is not None
        assert "{}" in str(default)
    finally:
        engine.dispose()
