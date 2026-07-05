"""Alembic 0039 — money columns float → NUMERIC(10,4) (plan 91 Phase 7.2).

The ALTER TYPE is Postgres-guarded; the sqlite round-trip proves the
migration is a clean no-op off Postgres, and the model assertions pin the
NUMERIC(10,4) + float-read (`asdecimal=False`) contract the code relies on.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from models import ApiUsage, GeneratedDocument

pytestmark = pytest.mark.uses_sample_data_shims

_PATH = (
    Path(__file__).resolve().parent.parent / "migrations" / "versions" / "0039_money_numeric.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("_alembic_0039", _PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_0039_chains_from_0038():
    migration = _load_migration()
    assert migration.revision == "0039_money_numeric"
    assert migration.down_revision == "0038_index_hygiene"


def test_models_declare_numeric_10_4_with_float_reads():
    for model in (ApiUsage, GeneratedDocument):
        col = model.__table__.c.cost_usd
        assert isinstance(col.type, sa.Numeric)
        assert (col.type.precision, col.type.scale) == (10, 4)
        assert col.type.asdecimal is False  # Python callers keep seeing floats


def test_0039_sqlite_roundtrip_is_noop(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'rt.sqlite'}")
    try:
        migration = _load_migration()
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()
                migration.downgrade()
    finally:
        engine.dispose()
