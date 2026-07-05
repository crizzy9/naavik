"""Alembic 0038 — index hygiene (plan 91 Phase 7.1).

The btree create/drop operations are dialect-portable, so the sqlite
round-trip exercises them for real against the tables built from current
model metadata; the trgm expression index is Postgres-guarded and covered
by the gated chain-replay suite. Static assertions pin the chain and the
model↔migration index agreement.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from models import Contact, Job, ProfileAnswer
from tests._sqlite import strip_pg_checks

pytestmark = pytest.mark.uses_sample_data_shims

_PATH = Path(__file__).resolve().parent.parent / "migrations" / "versions" / "0038_index_hygiene.py"


def _load_migration():
    spec = importlib.util.spec_from_file_location("_alembic_0038", _PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_0038_chains_from_0037():
    migration = _load_migration()
    assert migration.revision == "0038_index_hygiene"
    assert migration.down_revision == "0037_appeventkind_auto_apply_values"


def test_0038_role_trgm_is_postgres_guarded():
    source = _PATH.read_text()
    assert 'dialect.name == "postgresql"' in source
    assert "gin_trgm_ops" in source
    assert "IF NOT EXISTS ix_job_role_trgm" in source


def test_models_declare_the_added_indexes_and_not_the_dropped_ones():
    """Model metadata and migration 0038 agree, so --autogenerate stays quiet."""
    job_ix = {i.name for i in Job.__table__.indexes}
    contact_ix = {i.name for i in Contact.__table__.indexes}
    pa_ix = {i.name for i in ProfileAnswer.__table__.indexes}

    assert "ix_job_warm_intro_contact_id" in job_ix
    assert "ix_job_last_scrape_run_id" in job_ix
    assert "ix_contact_user_email" in contact_ix
    assert "ix_profile_answer_source_screener_answer_id" in pa_ix

    # Redundant duplicates are gone from the models too.
    assert "ix_job_found_at_desc" not in job_ix
    assert "ix_job_user_id" not in job_ix
    assert "ix_contact_user_id" not in contact_ix
    assert "ix_profile_answer_user_id" not in pa_ix


def _pre_0038_tables(engine) -> None:
    """Create job/contact/profile_answer + deps as they looked BEFORE 0038."""
    from models import Application, ApplicationScreenerAnswer, JobScrapeRun, User

    tables = strip_pg_checks(
        (User, Contact, JobScrapeRun, Job, Application, ApplicationScreenerAnswer, ProfileAnswer)
    )
    from sqlmodel import SQLModel

    with engine.begin() as conn:
        SQLModel.metadata.create_all(conn, tables=tables)
        # Recreate the pre-0038 shape: the dropped indexes existed, the added
        # ones didn't (models already reflect post-0038, so invert).
        conn.exec_driver_sql("CREATE INDEX ix_job_found_at_desc ON job (found_at)")
        conn.exec_driver_sql("CREATE INDEX ix_job_user_id ON job (user_id)")
        conn.exec_driver_sql("CREATE INDEX ix_contact_user_id ON contact (user_id)")
        conn.exec_driver_sql("CREATE INDEX ix_profile_answer_user_id ON profile_answer (user_id)")
        conn.exec_driver_sql("DROP INDEX ix_job_warm_intro_contact_id")
        conn.exec_driver_sql("DROP INDEX ix_job_last_scrape_run_id")
        conn.exec_driver_sql("DROP INDEX ix_contact_user_email")
        conn.exec_driver_sql("DROP INDEX ix_profile_answer_source_screener_answer_id")


def _index_names(engine, table: str) -> set[str]:
    with engine.connect() as conn:
        rows = conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=:t",
            {"t": table},
        ).fetchall()
    return {r[0] for r in rows}


def test_0038_sqlite_roundtrip(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'rt.sqlite'}")
    try:
        _pre_0038_tables(engine)
        migration = _load_migration()

        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()

        job_ix = _index_names(engine, "job")
        assert "ix_job_warm_intro_contact_id" in job_ix
        assert "ix_job_last_scrape_run_id" in job_ix
        assert "ix_job_found_at_desc" not in job_ix
        assert "ix_job_user_id" not in job_ix
        assert "ix_contact_user_email" in _index_names(engine, "contact")

        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.downgrade()

        job_ix = _index_names(engine, "job")
        assert "ix_job_found_at_desc" in job_ix
        assert "ix_job_warm_intro_contact_id" not in job_ix
    finally:
        engine.dispose()
