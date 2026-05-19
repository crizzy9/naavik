"""Alembic 0004 round-trip test — drops 5 vault-derived `Settings` columns.

Plan 26 (0.2.0.01) § D.9: verify the migration is reversible. Builds a
minimal `settings` table on a transient SQLite DB (stdlib `sqlite3` driver
via SQLAlchemy's sync engine; SQLite 3.35+ supports `ALTER TABLE DROP
COLUMN` natively). The full 0001/0002/0003 chain depends on pgvector and
Postgres-only types, so we sidestep them by stamping the alembic context
manually at 0003, exercising 0004's `upgrade()` + `downgrade()` directly,
and asserting the 5 columns disappear and reappear cleanly.

The 5 vault-derived columns under test:
- `llm_api_key_fingerprint`        (str, nullable)
- `discord_webhook_configured`     (bool, server_default=false)
- `telegram_bot_configured`        (bool, server_default=false)
- `portfolio_webhook_configured`   (bool, server_default=false)
- `scraper_proxy_configured`       (bool, server_default=false)
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

_VAULT_COLUMNS = (
    "llm_api_key_fingerprint",
    "discord_webhook_configured",
    "telegram_bot_configured",
    "portfolio_webhook_configured",
    "scraper_proxy_configured",
)


def _load_migration_0004():
    """Import the 0004 migration module from disk by path.

    Alembic migrations under `migrations/versions/` aren't a Python package;
    importing them via the alembic command surface requires a full env.py
    boot (which pulls pgvector). Direct-file load keeps the test scoped.
    """
    repo_root = Path(__file__).resolve().parent.parent
    path = repo_root / "migrations" / "versions" / "0004_drop_vault_columns.py"
    spec = importlib.util.spec_from_file_location("_alembic_0004", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_pre_0004_settings_table(engine: sa.Engine) -> None:
    """Stand up a `settings` table carrying the 5 vault-derived columns +
    a couple of innocuous columns so we can assert presence / absence
    without depending on the full prod schema.
    """
    metadata = sa.MetaData()
    sa.Table(
        "settings",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, nullable=False),
        sa.Column("llm_api_key_fingerprint", sa.String(), nullable=True),
        sa.Column(
            "discord_webhook_configured",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "telegram_bot_configured",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "portfolio_webhook_configured",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "scraper_proxy_configured",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    metadata.create_all(engine)


def _settings_columns(engine: sa.Engine) -> set[str]:
    inspector = sa.inspect(engine)
    return {col["name"] for col in inspector.get_columns("settings")}


def test_0004_upgrade_drops_vault_columns(tmp_path):
    db_path = tmp_path / "round_trip.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0004_settings_table(engine)
        pre_cols = _settings_columns(engine)
        for col in _VAULT_COLUMNS:
            assert col in pre_cols, f"precondition: {col!r} should exist pre-upgrade"

        migration = _load_migration_0004()
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()

        post_cols = _settings_columns(engine)
        for col in _VAULT_COLUMNS:
            assert col not in post_cols, f"{col!r} should be dropped after upgrade"
        # Innocuous columns survive.
        assert "id" in post_cols
        assert "user_id" in post_cols
    finally:
        engine.dispose()


def test_0004_downgrade_restores_vault_columns(tmp_path):
    db_path = tmp_path / "round_trip.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0004_settings_table(engine)
        migration = _load_migration_0004()

        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()

        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.downgrade()

        post_cols = _settings_columns(engine)
        for col in _VAULT_COLUMNS:
            assert col in post_cols, f"{col!r} should reappear after downgrade"

        # Verify nullability + defaults match the spec in the migration docstring:
        # fingerprint is nullable; the four booleans default to false.
        inspector = sa.inspect(engine)
        by_name = {c["name"]: c for c in inspector.get_columns("settings")}
        assert by_name["llm_api_key_fingerprint"]["nullable"] is True
        for bool_col in (
            "discord_webhook_configured",
            "telegram_bot_configured",
            "portfolio_webhook_configured",
            "scraper_proxy_configured",
        ):
            assert by_name[bool_col]["nullable"] is False, f"{bool_col} must be NOT NULL"
    finally:
        engine.dispose()


def test_0004_full_round_trip_is_idempotent(tmp_path):
    db_path = tmp_path / "round_trip.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0004_settings_table(engine)
        migration = _load_migration_0004()

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

        final_cols = _settings_columns(engine)
        for col in _VAULT_COLUMNS:
            assert col not in final_cols, f"{col!r} should be gone after upgrade→downgrade→upgrade"
        assert "id" in final_cols
        assert "user_id" in final_cols
    finally:
        engine.dispose()
