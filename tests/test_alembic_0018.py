"""Alembic 0018 round-trip — Application.generation_trace + 5 Settings.generation fields.

Plan 66 / 0.3.1. JSONB on Postgres, JSON on sqlite. sqlite-only smoke
test (table-shape assertion); Postgres-specific JSONB type exercised in
the live-DB suite.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def _load_migration_0018():
    repo_root = Path(__file__).resolve().parent.parent
    path = repo_root / "migrations" / "versions" / "0018_generation_trace_and_settings.py"
    spec = importlib.util.spec_from_file_location("_alembic_0018", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_pre_0018_tables(engine: sa.Engine) -> None:
    """Stub the minimal `application` + `settings` shape at post-0017."""
    metadata = sa.MetaData()
    sa.Table("user", metadata, sa.Column("id", sa.Integer, primary_key=True))
    sa.Table(
        "application",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, nullable=False),
        sa.Column("company", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="DRAFT"),
    )
    sa.Table(
        "settings",
        metadata,
        sa.Column("user_id", sa.Integer, primary_key=True),
        sa.Column("llm_provider", sa.String(), nullable=False, server_default="anthropic"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    metadata.create_all(engine)


def _table_columns(engine: sa.Engine, table: str) -> set[str]:
    inspector = sa.inspect(engine)
    if table not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns(table)}


def test_0018_upgrade_adds_generation_trace_and_settings_fields(tmp_path):
    db_path = tmp_path / "rt.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0018_tables(engine)
        migration = _load_migration_0018()
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()

        app_cols = _table_columns(engine, "application")
        assert "generation_trace" in app_cols

        settings_cols = _table_columns(engine, "settings")
        for required in (
            "ai_writing_voice_samples",
            "cover_letter_format",
            "tier_2_evasion_enabled",
            "resume_template_preference",
            "parse_fidelity_threshold",
        ):
            assert required in settings_cols, required
    finally:
        engine.dispose()


def test_0018_downgrade_drops_all_added_columns(tmp_path):
    db_path = tmp_path / "rt.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0018_tables(engine)
        migration = _load_migration_0018()
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.downgrade()

        assert "generation_trace" not in _table_columns(engine, "application")
        settings_cols = _table_columns(engine, "settings")
        for absent in (
            "ai_writing_voice_samples",
            "cover_letter_format",
            "tier_2_evasion_enabled",
            "resume_template_preference",
            "parse_fidelity_threshold",
        ):
            assert absent not in settings_cols
    finally:
        engine.dispose()


def test_0018_full_round_trip_is_idempotent(tmp_path):
    db_path = tmp_path / "rt.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0018_tables(engine)
        migration = _load_migration_0018()
        for step in ("upgrade", "downgrade", "upgrade"):
            with engine.begin() as conn:
                ctx = MigrationContext.configure(conn)
                with Operations.context(ctx):
                    getattr(migration, step)()
        assert "generation_trace" in _table_columns(engine, "application")
        assert "ai_writing_voice_samples" in _table_columns(engine, "settings")
    finally:
        engine.dispose()
