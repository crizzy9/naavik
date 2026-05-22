"""Alembic 0016 round-trip — Settings.auto_apply_adapter_confidence_threshold.

Plan 63 / 0.2.7.10 § D.5 + § G. Mirrors `tests/test_alembic_0011.py` shape
(additive column on `settings` with `server_default`). Plant a minimal pre-0016
`settings` table; exercise upgrade + downgrade + idempotent triple.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

pytestmark = pytest.mark.uses_sample_data_shims


def _load_migration_0016():
    repo_root = Path(__file__).resolve().parent.parent
    path = repo_root / "migrations" / "versions" / "0016_ats_adapter_confidence_threshold.py"
    spec = importlib.util.spec_from_file_location("_alembic_0016", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_pre_0016_settings(engine: sa.Engine) -> None:
    """Plant a minimal `settings` shell — the column is what 0016 owns."""
    metadata = sa.MetaData()
    sa.Table(
        "settings",
        metadata,
        sa.Column("user_id", sa.Integer, primary_key=True),
        sa.Column("llm_provider", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    metadata.create_all(engine)


def _settings_columns(engine: sa.Engine) -> set[str]:
    inspector = sa.inspect(engine)
    return {col["name"] for col in inspector.get_columns("settings")}


def test_0016_upgrade_adds_threshold_column(tmp_path):
    db_path = tmp_path / "rt.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0016_settings(engine)
        assert "auto_apply_adapter_confidence_threshold" not in _settings_columns(engine)

        migration = _load_migration_0016()
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()

        assert "auto_apply_adapter_confidence_threshold" in _settings_columns(engine)
    finally:
        engine.dispose()


def test_0016_downgrade_drops_threshold_column(tmp_path):
    db_path = tmp_path / "rt.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0016_settings(engine)
        migration = _load_migration_0016()
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.downgrade()

        assert "auto_apply_adapter_confidence_threshold" not in _settings_columns(engine)
    finally:
        engine.dispose()


def test_0016_full_round_trip_is_idempotent(tmp_path):
    db_path = tmp_path / "rt.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0016_settings(engine)
        migration = _load_migration_0016()
        for step in ("upgrade", "downgrade", "upgrade"):
            with engine.begin() as conn:
                ctx = MigrationContext.configure(conn)
                with Operations.context(ctx):
                    getattr(migration, step)()
        assert "auto_apply_adapter_confidence_threshold" in _settings_columns(engine)
    finally:
        engine.dispose()


def test_0016_server_default_is_zero_point_seven(tmp_path):
    """`server_default=0.7` matches plan § D.5 locked default."""
    db_path = tmp_path / "rt.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0016_settings(engine)
        migration = _load_migration_0016()
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()

        # Insert a row WITHOUT the new column; the server_default fills it in.
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO settings (user_id, llm_provider, created_at, updated_at) "
                    "VALUES (1, 'anthropic', '2026-05-20', '2026-05-20')"
                )
            )
        with engine.begin() as conn:
            row = conn.execute(
                sa.text(
                    "SELECT auto_apply_adapter_confidence_threshold FROM settings WHERE user_id = 1"
                )
            ).first()
        assert row is not None
        assert abs(row[0] - 0.7) < 1e-9
    finally:
        engine.dispose()
