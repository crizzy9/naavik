"""Alembic 0037 — backfill AppEventKind AUTO_APPLY_* enum values.

Plan 91 Phase 1.5. The `ADD VALUE` statements are Postgres-only (guarded), so
the sqlite round-trip just proves the migration is a clean no-op off Postgres;
the static assertions prove it emits the right labels and chains correctly.
Full Postgres emission is exercised by the gated chain-replay suite.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

pytestmark = pytest.mark.uses_sample_data_shims

_PATH = (
    Path(__file__).resolve().parent.parent
    / "migrations"
    / "versions"
    / "0037_appeventkind_auto_apply_values.py"
)
_NEW_VALUES = (
    "AUTO_APPLY_DRY_RUN",
    "AUTO_APPLY_DRAINED",
    "AUTO_APPLY_VISA_BLOCKED",
    "AUTO_APPLY_QUEUED",
)


def _load_migration_0037():
    spec = importlib.util.spec_from_file_location("_alembic_0037", _PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_0037_chains_from_0036():
    migration = _load_migration_0037()
    assert migration.revision == "0037_appeventkind_auto_apply_values"
    assert migration.down_revision == "0036_section_selection_override"


def test_0037_adds_all_four_labels_matching_enum():
    from models.enums import AppEventKind

    migration = _load_migration_0037()
    # The migration's tuple is the source of truth for what gets added.
    assert set(migration._NEW_VALUES) == set(_NEW_VALUES)
    for value in _NEW_VALUES:
        # The label must equal the Python member NAME (SQLAlchemy binds names).
        assert getattr(AppEventKind, value).name == value


def test_0037_emits_add_value_and_guards_postgres():
    source = _PATH.read_text()
    assert "ADD VALUE IF NOT EXISTS" in source
    assert "appeventkind" in source
    assert "autocommit_block" in source
    assert 'dialect.name != "postgresql"' in source


def test_0037_sqlite_roundtrip_is_noop(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'rt.sqlite'}")
    try:
        migration = _load_migration_0037()
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()
                migration.downgrade()
    finally:
        engine.dispose()
