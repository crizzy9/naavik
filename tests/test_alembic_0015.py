"""Alembic 0015 round-trip — partial unique index `WHERE status='ACTIVE'`.

Plan 62 / 0.2.7.07 (hacker MED-1 fix). Mirrors `tests/test_alembic_0014.py`
shape. The index is the DB-level invariant that makes two concurrent ACTIVE
rows per tenant impossible — rotate_tenant_key's race window now surfaces as
IntegrityError instead of two-ACTIVE-row data corruption.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def _load_migration(name: str):
    repo_root = Path(__file__).resolve().parent.parent
    path = repo_root / "migrations" / "versions" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_alembic_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_pre_0015_schema(engine: sa.Engine) -> None:
    """Apply 0014 to produce the schema 0015 expects."""
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
    migration_0014 = _load_migration("0014_tenant_signing_keys")
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            migration_0014.upgrade()


def _index_names(engine: sa.Engine, table: str) -> set[str]:
    inspector = sa.inspect(engine)
    return {idx["name"] for idx in inspector.get_indexes(table)}


def test_0015_upgrade_creates_partial_unique_index(tmp_path):
    db_path = tmp_path / "rt.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0015_schema(engine)
        before = _index_names(engine, "tenant_signing_key")
        assert "ix_tenant_signing_key_one_active_per_tenant" not in before

        migration = _load_migration("0015_tenant_signing_key_active_uniq")
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()

        after = _index_names(engine, "tenant_signing_key")
        assert "ix_tenant_signing_key_one_active_per_tenant" in after
    finally:
        engine.dispose()


def test_0015_downgrade_drops_index(tmp_path):
    db_path = tmp_path / "rt.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0015_schema(engine)
        migration = _load_migration("0015_tenant_signing_key_active_uniq")
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.downgrade()

        after = _index_names(engine, "tenant_signing_key")
        assert "ix_tenant_signing_key_one_active_per_tenant" not in after
    finally:
        engine.dispose()


def test_0015_full_round_trip_is_idempotent(tmp_path):
    db_path = tmp_path / "rt.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0015_schema(engine)
        migration = _load_migration("0015_tenant_signing_key_active_uniq")
        for step in ("upgrade", "downgrade", "upgrade"):
            with engine.begin() as conn:
                ctx = MigrationContext.configure(conn)
                with Operations.context(ctx):
                    getattr(migration, step)()
        assert "ix_tenant_signing_key_one_active_per_tenant" in _index_names(
            engine, "tenant_signing_key"
        )
    finally:
        engine.dispose()


def test_0015_partial_index_blocks_two_active_rows(tmp_path):
    """End-to-end: after 0015 lands, two ACTIVE rows for same tenant raise."""
    db_path = tmp_path / "uniq.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0015_schema(engine)
        migration = _load_migration("0015_tenant_signing_key_active_uniq")
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()

        with engine.begin() as conn:
            # 0014 backfill already planted the env-legacy ACTIVE row for
            # tenant_id=1. Attempting a second ACTIVE for the same tenant
            # must violate the partial unique index.
            try:
                conn.execute(
                    sa.text(
                        "INSERT INTO tenant_signing_key "
                        "(tenant_id, kid, algorithm, status, "
                        "public_key_pem, private_key_pem, created_at) "
                        "VALUES (1, 'kid-second-active', 'RS256', 'ACTIVE', "
                        "'public', 'private', :now)"
                    ).bindparams(now="2026-05-20 00:00:00")
                )
                raised = False
            except sa.exc.IntegrityError:
                raised = True
            assert raised, "partial unique index did not fire"
    finally:
        engine.dispose()
