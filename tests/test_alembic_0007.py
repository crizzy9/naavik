"""Alembic 0007 round-trip — Settings scraper inputs + fail counter.

Plan 35 (0.2.0.10). Verifies the migration is reversible. Mirrors the
structure of `tests/test_alembic_0006.py`.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

pytestmark = pytest.mark.uses_sample_data_shims


def _load_migration_0007():
    repo_root = Path(__file__).resolve().parent.parent
    path = repo_root / "migrations" / "versions" / "0007_settings_scraper_inputs.py"
    spec = importlib.util.spec_from_file_location("_alembic_0007", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_pre_0007_settings_table(engine: sa.Engine) -> None:
    """Stand up a `settings` table at the post-0006 shape, minus the
    new columns. Only the column the migration touches are checked.
    """
    metadata = sa.MetaData()
    sa.Table(
        "settings",
        metadata,
        sa.Column("user_id", sa.Integer, primary_key=True),
        sa.Column("llm_provider", sa.String(), nullable=False),
        sa.Column("workday_companies", sa.String(), nullable=False, server_default="{}"),
        sa.Column("sources_enabled", sa.String(), nullable=False, server_default="{}"),
        sa.Column("source_schedules", sa.String(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    metadata.create_all(engine)


def _settings_columns(engine: sa.Engine) -> set[str]:
    inspector = sa.inspect(engine)
    return {col["name"] for col in inspector.get_columns("settings")}


def test_0007_upgrade_adds_five_columns(tmp_path):
    db_path = tmp_path / "round_trip.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0007_settings_table(engine)
        before = _settings_columns(engine)
        for new_col in (
            "linkedin_keywords",
            "linkedin_location",
            "indeed_keywords",
            "indeed_location",
            "consecutive_scrape_failures",
        ):
            assert new_col not in before

        migration = _load_migration_0007()
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()

        after = _settings_columns(engine)
        for new_col in (
            "linkedin_keywords",
            "linkedin_location",
            "indeed_keywords",
            "indeed_location",
            "consecutive_scrape_failures",
        ):
            assert new_col in after
    finally:
        engine.dispose()


def test_0007_downgrade_drops_five_columns(tmp_path):
    db_path = tmp_path / "round_trip.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0007_settings_table(engine)
        migration = _load_migration_0007()

        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.downgrade()

        after = _settings_columns(engine)
        for new_col in (
            "linkedin_keywords",
            "linkedin_location",
            "indeed_keywords",
            "indeed_location",
            "consecutive_scrape_failures",
        ):
            assert new_col not in after
    finally:
        engine.dispose()


def test_0007_full_round_trip_is_idempotent(tmp_path):
    db_path = tmp_path / "round_trip.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0007_settings_table(engine)
        migration = _load_migration_0007()

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
        assert "linkedin_keywords" in after
        assert "consecutive_scrape_failures" in after
    finally:
        engine.dispose()
