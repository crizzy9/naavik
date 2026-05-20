"""Alembic 0009 round-trip — APScheduler jobstore pickle → JSON rewrite.

Per docs/plans/48-0.2.0.10b-pickle-deser-replacement.md § D.5.

Stand up a sqlite-backed `apscheduler_jobs` table populated by a real
`SQLAlchemyJobStore` (pickle path). Apply 0009 upgrade. Assert every
row is now JSON. Apply downgrade. Assert every row is pickle again.

Also exercises the table-absent guard — running upgrade against a
fresh SQLite engine with no `apscheduler_jobs` table is a no-op.
"""

from __future__ import annotations

import importlib.util
import os
import pickle
from datetime import UTC, datetime
from pathlib import Path

# Bypass SECRET_KEY validator so `from scheduler.json_jobstore import ...`
# (transitively imports config) doesn't raise at collection.
os.environ.setdefault("NAAVIK_DEBUG", "1")

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from apscheduler.job import Job
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger


def _load_migration_0009():
    repo_root = Path(__file__).resolve().parent.parent
    path = repo_root / "migrations" / "versions" / "0009_pickle_to_json_jobs.py"
    spec = importlib.util.spec_from_file_location("_alembic_0009", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seed_apscheduler_jobs_pickle(engine: sa.Engine) -> dict[str, bytes]:
    """Add three jobs via vanilla SQLAlchemyJobStore (pickle path). Return id->blob."""
    from scheduler import jobs as scheduler_jobs
    from scheduler import scraping as scheduler_scraping

    store = SQLAlchemyJobStore(engine=engine)
    scheduler = BackgroundScheduler(jobstores={"default": store})
    store.start(scheduler, alias="default")

    cron_trigger = CronTrigger.from_crontab("*/5 * * * *", timezone="UTC")
    interval_trigger = IntervalTrigger(minutes=90, jitter=30, timezone="UTC")

    fixtures = [
        ("j.cron", scheduler_jobs.auto_apply, cron_trigger),
        ("j.interval", scheduler_scraping.scrape_indeed, interval_trigger),
        ("j.cron2", scheduler_jobs.aggregate_costs, CronTrigger(hour=0, minute=30, timezone="UTC")),
    ]
    for job_id, func, trigger in fixtures:
        job = Job(
            scheduler,
            id=job_id,
            func=func,
            trigger=trigger,
            args=(),
            kwargs={},
            misfire_grace_time=1,
            coalesce=True,
            max_instances=1,
            next_run_time=datetime(2026, 1, 1, tzinfo=UTC),
            executor="default",
        )
        store.add_job(job)

    # Snapshot raw blobs (pickle path).
    with engine.begin() as conn:
        rows = conn.execute(sa.text("SELECT id, job_state FROM apscheduler_jobs")).fetchall()
    return {row[0]: bytes(row[1]) for row in rows}


def _run_upgrade(engine: sa.Engine, migration) -> None:
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            migration.upgrade()


def _run_downgrade(engine: sa.Engine, migration) -> None:
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            migration.downgrade()


def test_0009_upgrade_rewrites_pickle_to_json(tmp_path):
    """All pickle rows become JSON after upgrade."""
    db_path = tmp_path / "0009.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        before = _seed_apscheduler_jobs_pickle(engine)
        # Sanity: first byte is the pickle proto marker.
        for _id, blob in before.items():
            assert blob[0] == 0x80, f"expected pickle proto, got {blob[0]:#x} for {_id}"

        migration = _load_migration_0009()
        _run_upgrade(engine, migration)

        with engine.begin() as conn:
            rows = conn.execute(
                sa.text("SELECT id, job_state FROM apscheduler_jobs ORDER BY id")
            ).fetchall()
        assert len(rows) == 3
        for row in rows:
            blob = bytes(row[1])
            # JSON-encoded payload starts with `{` (0x7b).
            assert blob[0:1] == b"{", f"expected JSON, got first-byte={blob[0]:#x} for {row[0]}"
    finally:
        engine.dispose()


def test_0009_round_trip_preserves_func_ref(tmp_path):
    """Upgrade -> reading via NaavikJsonJobStore -> downgrade -> pickle path lossless."""
    from scheduler.json_jobstore import NaavikJsonJobStore

    db_path = tmp_path / "0009-rt.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _seed_apscheduler_jobs_pickle(engine)
        migration = _load_migration_0009()
        _run_upgrade(engine, migration)

        # Read via new store — func_ref + trigger types preserved.
        json_store = NaavikJsonJobStore(engine=engine)
        scheduler = BackgroundScheduler(jobstores={"default": json_store})
        json_store.start(scheduler, alias="default")
        jobs = {j.id: j for j in json_store.get_all_jobs()}
        assert set(jobs.keys()) == {"j.cron", "j.interval", "j.cron2"}
        assert jobs["j.cron"].func_ref == "scheduler.jobs:auto_apply"
        assert jobs["j.interval"].func_ref == "scheduler.scraping:scrape_indeed"
        assert jobs["j.cron2"].func_ref == "scheduler.jobs:aggregate_costs"
        assert isinstance(jobs["j.cron"].trigger, CronTrigger)
        assert isinstance(jobs["j.interval"].trigger, IntervalTrigger)
        assert jobs["j.interval"].trigger.interval.total_seconds() == 5400

        # Downgrade back to pickle — read via vanilla store.
        _run_downgrade(engine, migration)
        with engine.begin() as conn:
            rows = conn.execute(sa.text("SELECT id, job_state FROM apscheduler_jobs")).fetchall()
        for row in rows:
            blob = bytes(row[1])
            assert blob[0] == 0x80
            state = pickle.loads(blob)  # noqa: S301 — test-only round-trip
            assert state["func"] in {
                "scheduler.jobs:auto_apply",
                "scheduler.scraping:scrape_indeed",
                "scheduler.jobs:aggregate_costs",
            }
    finally:
        engine.dispose()


def test_0009_upgrade_table_absent_is_noop(tmp_path):
    """Fresh DB with no apscheduler_jobs table — upgrade is a no-op + INFO log."""
    db_path = tmp_path / "0009-empty.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        migration = _load_migration_0009()
        _run_upgrade(engine, migration)

        inspector = sa.inspect(engine)
        assert "apscheduler_jobs" not in inspector.get_table_names()
    finally:
        engine.dispose()


def test_0009_upgrade_skips_non_decodable_row(tmp_path):
    """Corrupt pickle row is logged + skipped; migration completes."""
    db_path = tmp_path / "0009-corrupt.sqlite"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        _seed_apscheduler_jobs_pickle(engine)
        # Tamper one row with garbage bytes that look like pickle but aren't.
        with engine.begin() as conn:
            conn.execute(
                sa.text("UPDATE apscheduler_jobs SET job_state = :s WHERE id = 'j.cron'"),
                {"s": b"\x80\x05not-pickle-content"},
            )

        migration = _load_migration_0009()
        _run_upgrade(engine, migration)

        # Other two rows should have been rewritten; the corrupt row remains
        # (pickle-prefix sniff passed, pickle.loads failed, row skipped).
        with engine.begin() as conn:
            rows = conn.execute(
                sa.text("SELECT id, job_state FROM apscheduler_jobs ORDER BY id")
            ).fetchall()
        rows_by_id = {r[0]: bytes(r[1]) for r in rows}
        assert rows_by_id["j.interval"][0:1] == b"{"
        assert rows_by_id["j.cron2"][0:1] == b"{"
        # Corrupt row left in pickle-byte form for the next scheduler boot
        # to sweep via _get_jobs reconstitute-failed cleanup.
        assert rows_by_id["j.cron"][0] == 0x80
    finally:
        engine.dispose()
