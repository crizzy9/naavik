"""Alembic 0012 round-trip — ProfileAnswer reuse cache.

Plan 61 / 0.2.7.14. Mirrors `tests/test_alembic_0008.py`. Stand up the
upstream tables (`user` + `application_screener_answer`) as minimal sqlite
shells so the FK targets exist, then exercise 0012's upgrade + downgrade.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def _load_migration_0012():
    repo_root = Path(__file__).resolve().parent.parent
    path = repo_root / "migrations" / "versions" / "0012_profile_answer.py"
    spec = importlib.util.spec_from_file_location("_alembic_0012", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_pre_0012_tables(engine: sa.Engine) -> None:
    """Stub the FK target tables: `user` + `application_screener_answer`."""
    metadata = sa.MetaData()
    sa.Table(
        "user",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
    )
    sa.Table(
        "application_screener_answer",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
    )
    metadata.create_all(engine)


def _profile_answer_columns(engine: sa.Engine) -> set[str]:
    inspector = sa.inspect(engine)
    if "profile_answer" not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns("profile_answer")}


def _profile_answer_indexes(engine: sa.Engine) -> set[str]:
    inspector = sa.inspect(engine)
    if "profile_answer" not in inspector.get_table_names():
        return set()
    return {idx["name"] for idx in inspector.get_indexes("profile_answer")}


def _profile_answer_uniques(engine: sa.Engine) -> set[str]:
    inspector = sa.inspect(engine)
    if "profile_answer" not in inspector.get_table_names():
        return set()
    return {uc["name"] for uc in inspector.get_unique_constraints("profile_answer")}


def test_0012_upgrade_creates_profile_answer(tmp_path):
    db_path = tmp_path / "rt.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0012_tables(engine)
        assert "profile_answer" not in sa.inspect(engine).get_table_names()

        migration = _load_migration_0012()
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()

        cols = _profile_answer_columns(engine)
        for required in (
            "id",
            "user_id",
            "question_fingerprint",
            "question_text_sample",
            "answer",
            "source_screener_answer_id",
            "times_offered",
            "times_accepted",
            "last_used_at",
            "created_at",
            "updated_at",
        ):
            assert required in cols, required

        assert "ix_profile_answer_user_last_used" in _profile_answer_indexes(engine)
        assert "uq_profile_answer_user_fingerprint" in _profile_answer_uniques(engine)
    finally:
        engine.dispose()


def test_0012_downgrade_drops_profile_answer(tmp_path):
    db_path = tmp_path / "rt.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0012_tables(engine)
        migration = _load_migration_0012()
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.downgrade()

        assert "profile_answer" not in sa.inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_0012_full_round_trip_is_idempotent(tmp_path):
    db_path = tmp_path / "rt.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _build_pre_0012_tables(engine)
        migration = _load_migration_0012()
        for step in ("upgrade", "downgrade", "upgrade"):
            with engine.begin() as conn:
                ctx = MigrationContext.configure(conn)
                with Operations.context(ctx):
                    getattr(migration, step)()
        assert "profile_answer" in sa.inspect(engine).get_table_names()
    finally:
        engine.dispose()
