"""Alembic 0014 round-trip — tenant + tenant_signing_key + Settings cols.

Plan 62 / 0.2.7.07. Mirrors `tests/test_alembic_0013.py` shape. sqlite
backs the round-trip; the Postgres ENUM types are no-ops there.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def _load_migration_0014():
    repo_root = Path(__file__).resolve().parent.parent
    path = repo_root / "migrations" / "versions" / "0014_tenant_signing_keys.py"
    spec = importlib.util.spec_from_file_location("_alembic_0014", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_pre_0014_settings_table(engine: sa.Engine) -> None:
    """Stand up `settings` at the post-0013 shape minus the new JWT columns."""
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


def _table_columns(engine: sa.Engine, table: str) -> set[str]:
    inspector = sa.inspect(engine)
    if table not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns(table)}


def test_0014_upgrade_creates_tables_and_columns(tmp_path):
    db_path = tmp_path / "rt.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0014_settings_table(engine)
        migration = _load_migration_0014()
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()

        names = set(sa.inspect(engine).get_table_names())
        assert "tenant" in names
        assert "tenant_signing_key" in names

        for col in (
            "id",
            "tenant_id",
            "kid",
            "algorithm",
            "status",
            "public_key_pem",
            "private_key_pem",
            "created_at",
            "activated_at",
            "retired_at",
        ):
            assert col in _table_columns(engine, "tenant_signing_key")

        settings_cols = _table_columns(engine, "settings")
        assert "jwt_rotation_days" in settings_cols
        assert "jwt_rotation_grace_days" in settings_cols
    finally:
        engine.dispose()


def test_0014_backfill_inserts_env_legacy_row(tmp_path, monkeypatch):
    db_path = tmp_path / "rt.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0014_settings_table(engine)
        monkeypatch.setenv("SECRET_KEY", "deterministic-test-secret-key-32+bytes")

        migration = _load_migration_0014()
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()

        with engine.connect() as conn:
            rows = conn.execute(sa.text("SELECT * FROM tenant")).all()
            assert len(rows) == 1
            assert rows[0][1] == "self-hosted"

            rows = conn.execute(
                sa.text("SELECT kid, algorithm, status, private_key_pem FROM tenant_signing_key")
            ).all()
            assert len(rows) == 1
            kid, algorithm, status, secret = rows[0]
            assert kid == "env-legacy"
            assert algorithm == "HS256"
            assert status == "ACTIVE"
            assert secret == "deterministic-test-secret-key-32+bytes"
    finally:
        engine.dispose()
        os.environ.pop("SECRET_KEY", None)


def test_0014_downgrade_drops_tables_and_columns(tmp_path):
    db_path = tmp_path / "rt.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0014_settings_table(engine)
        migration = _load_migration_0014()
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.downgrade()

        names = set(sa.inspect(engine).get_table_names())
        assert "tenant" not in names
        assert "tenant_signing_key" not in names
        settings_cols = _table_columns(engine, "settings")
        assert "jwt_rotation_days" not in settings_cols
        assert "jwt_rotation_grace_days" not in settings_cols
    finally:
        engine.dispose()


def test_0014_full_round_trip_is_idempotent(tmp_path):
    db_path = tmp_path / "rt.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0014_settings_table(engine)
        migration = _load_migration_0014()
        for step in ("upgrade", "downgrade", "upgrade"):
            with engine.begin() as conn:
                ctx = MigrationContext.configure(conn)
                with Operations.context(ctx):
                    getattr(migration, step)()
        assert "tenant_signing_key" in sa.inspect(engine).get_table_names()
    finally:
        engine.dispose()
