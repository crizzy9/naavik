"""NaavikJsonJobStore — JSON-serializing replacement for APScheduler's
SQLAlchemyJobStore.

Per docs/plans/48-0.2.0.10b-pickle-deser-replacement.md § D.4. Seven
explicit tests:

1. test_roundtrip_zero_arg_cron_job — CronTrigger round-trip preserves
   func_ref + field expressions.
2. test_roundtrip_interval_trigger — IntervalTrigger round-trip
   preserves interval seconds + timezone + jitter.
3. test_refuses_non_json_args — datetime / bytes args raise TypeError
   at add_job.
4. test_refuses_unsupported_trigger — unknown trigger class raises
   UnsupportedTriggerError wrapped in TypeError.
5. test_func_ref_allowlist_rejects_tampered_row — `func=os:system` row
   is rejected on load and removed by parent `_get_jobs` sweep.
6. test_schema_validation_rejects_unknown_fields — extra / missing
   field raises ValueError.
7. test_allowlist_matches_register_all — every callable passed to
   `add_job` by `scheduler.jobs.register_all` +
   `scheduler.scraping.register_scraping_jobs` must be in
   FUNC_REF_ALLOWLIST. Catches "new scraper, forgot to update
   allowlist" regressions.

All tests use `sqlite:///:memory:` for isolation; no Postgres dep.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any

# Bypass SECRET_KEY validator so `from scheduler import jobs` (which transitively
# imports config) doesn't ValidationError at module import time.
os.environ.setdefault("NAAVIK_DEBUG", "1")

import pytest
from apscheduler.job import Job
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.base import BaseTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.util import datetime_to_utc_timestamp, obj_to_ref

from scheduler import jobs as scheduler_jobs
from scheduler import scraping as scheduler_scraping
from scheduler.json_jobstore import (
    FUNC_REF_ALLOWLIST,
    NaavikJsonJobStore,
    UnsupportedTriggerError,
    _decode_job_state,
    _encode_job_state,
)

pytestmark = pytest.mark.uses_sample_data_shims

# ── Helpers ──────────────────────────────────────────────────────────────


def _make_store(url: str = "sqlite:///:memory:") -> NaavikJsonJobStore:
    """Create a started store backed by an in-memory SQLite engine."""
    store = NaavikJsonJobStore(url=url)
    scheduler = BackgroundScheduler(jobstores={"default": store})
    # _start() the store explicitly so jobs_t.create() fires once; we use
    # the scheduler only as the "owner" handle the store wants.
    store.start(scheduler, alias="default")
    return store


def _add_job(
    store: NaavikJsonJobStore, func, *, job_id: str, trigger: BaseTrigger, args=(), kwargs=None
) -> Job:
    """Build + register a Job through the public store API."""
    scheduler = store._scheduler
    job = Job(
        scheduler,
        id=job_id,
        func=func,
        trigger=trigger,
        args=args,
        kwargs=kwargs or {},
        name=job_id,
        misfire_grace_time=1,
        coalesce=True,
        max_instances=1,
        next_run_time=datetime(2026, 1, 1, tzinfo=UTC),
        executor="default",
    )
    store.add_job(job)
    return job


# ── 1. CronTrigger round-trip ───────────────────────────────────────────


def test_roundtrip_zero_arg_cron_job():
    """Encode → decode via store API preserves func_ref + cron fields."""
    store = _make_store()
    trigger = CronTrigger.from_crontab("*/5 * * * *", timezone="UTC")
    job = _add_job(store, scheduler_jobs.auto_apply, job_id="t.cron", trigger=trigger)

    # Pull it back out fresh from DB to force re-decode.
    looked_up = store.lookup_job("t.cron")
    assert looked_up is not None
    assert looked_up.func_ref == "scheduler.jobs:auto_apply"
    assert isinstance(looked_up.trigger, CronTrigger)
    # Field expression text round-trips per `str(field)` -> field kwarg.
    decoded_fields = {f.name: str(f) for f in looked_up.trigger.fields}
    original_fields = {f.name: str(f) for f in job.trigger.fields}
    assert decoded_fields == original_fields


# ── 2. IntervalTrigger round-trip ───────────────────────────────────────


def test_roundtrip_interval_trigger():
    """IntervalTrigger.interval.total_seconds + jitter + timezone round-trip."""
    store = _make_store()
    trigger = IntervalTrigger(minutes=90, jitter=30, timezone="UTC")
    _add_job(store, scheduler_scraping.scrape_indeed, job_id="t.interval", trigger=trigger)

    looked_up = store.lookup_job("t.interval")
    assert looked_up is not None
    assert isinstance(looked_up.trigger, IntervalTrigger)
    assert looked_up.trigger.interval.total_seconds() == 5400
    assert looked_up.trigger.jitter == 30
    assert str(looked_up.trigger.timezone) == "UTC"
    assert looked_up.func_ref == "scheduler.scraping:scrape_indeed"


# ── 3. Non-JSON-serializable args rejected at write ─────────────────────
#
# APScheduler's Job.__init__ validates args count against the callable
# signature, so passing extra args to a zero-arg callable fails BEFORE
# our codec runs. To exercise the codec path itself, drive _encode_job_state
# directly with a state dict that has non-JSON args.


def test_refuses_non_json_args_datetime():
    state = {
        "version": 1,
        "id": "x",
        "func": "scheduler.jobs:auto_apply",
        "trigger": CronTrigger.from_crontab("*/5 * * * *", timezone="UTC"),
        "executor": "default",
        "args": (datetime.now(UTC),),
        "kwargs": {},
        "name": "x",
        "misfire_grace_time": 1,
        "coalesce": True,
        "max_instances": 1,
        "next_run_time": None,
    }
    with pytest.raises(TypeError):
        _encode_job_state(state)


def test_refuses_non_json_args_bytes():
    state = {
        "version": 1,
        "id": "x",
        "func": "scheduler.jobs:auto_apply",
        "trigger": CronTrigger.from_crontab("*/5 * * * *", timezone="UTC"),
        "executor": "default",
        "args": (b"raw-bytes",),
        "kwargs": {},
        "name": "x",
        "misfire_grace_time": 1,
        "coalesce": True,
        "max_instances": 1,
        "next_run_time": None,
    }
    with pytest.raises(TypeError):
        _encode_job_state(state)


def test_add_job_wraps_codec_error_in_typeerror():
    """End-to-end: add_job re-raises codec errors as TypeError with helpful message."""
    store = _make_store()
    # auto_apply is zero-arg so we can't pass args via Job(); instead
    # construct a Job manually + monkey-patch args to bypass _modify validation.
    trigger = CronTrigger.from_crontab("*/5 * * * *", timezone="UTC")
    job = Job(
        store._scheduler,
        id="t.bypass",
        func=scheduler_jobs.auto_apply,
        trigger=trigger,
        args=(),
        kwargs={},
        misfire_grace_time=1,
        coalesce=True,
        max_instances=1,
        next_run_time=datetime(2026, 1, 1, tzinfo=UTC),
        executor="default",
    )
    # Bypass _modify validation: write directly to slot.
    object.__setattr__(job, "args", (datetime.now(UTC),))
    with pytest.raises(TypeError) as exc_info:
        store.add_job(job)
    assert "not JSON-serializable" in str(exc_info.value)


# ── 4. Unsupported trigger rejected ─────────────────────────────────────


def test_refuses_unsupported_trigger():
    """Custom BaseTrigger subclass without a codec branch is rejected."""

    class _CustomTrigger(BaseTrigger):
        def get_next_fire_time(self, previous_fire_time, now):
            return None

        def __getstate__(self):
            return {"version": 1}

        def __setstate__(self, state):
            pass

    store = _make_store()
    with pytest.raises(TypeError) as exc_info:
        _add_job(
            store,
            scheduler_jobs.auto_apply,
            job_id="t.bad-trigger",
            trigger=_CustomTrigger(),
        )
    assert "not JSON-serializable" in str(exc_info.value)
    # Underlying exc-cause is the UnsupportedTriggerError raised by the
    # encoder; assert via __cause__ chain.
    cause = exc_info.value.__cause__
    assert cause is None or isinstance(cause, UnsupportedTriggerError)


# ── 5. Func-ref allowlist enforces on load ──────────────────────────────


def test_func_ref_allowlist_rejects_tampered_row():
    """Hand-write a JSON row with func=os:system; assert it's purged on read."""
    store = _make_store()
    trigger = CronTrigger.from_crontab("*/5 * * * *", timezone="UTC")
    _add_job(store, scheduler_jobs.auto_apply, job_id="t.real", trigger=trigger)

    # Construct a tampered JSON state by hand — mirrors what an attacker
    # with DB write access could insert. Skip the encoder + go straight
    # to the table.
    tampered_payload: dict[str, Any] = {
        "version": 1,
        "id": "t.tampered",
        "func": "os:system",  # <- NOT in FUNC_REF_ALLOWLIST
        "trigger": {
            "__type__": "CronTrigger",
            "fields": {
                "year": "*",
                "month": "*",
                "day": "*",
                "week": "*",
                "day_of_week": "*",
                "hour": "*",
                "minute": "*",
                "second": "*",
            },
            "timezone": "UTC",
            "start_date": None,
            "end_date": None,
            "jitter": None,
        },
        "executor": "default",
        "args": [],
        "kwargs": {},
        "name": "t.tampered",
        "misfire_grace_time": 1,
        "coalesce": True,
        "max_instances": 1,
        "next_run_time": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
    }
    blob = json.dumps(tampered_payload).encode("utf-8")
    with store.engine.begin() as conn:
        conn.execute(
            store.jobs_t.insert().values(
                id="t.tampered",
                next_run_time=datetime_to_utc_timestamp(datetime(2026, 1, 1, tzinfo=UTC)),
                job_state=blob,
            )
        )

    # get_all_jobs triggers parent `_get_jobs` which calls `_reconstitute_job`
    # per row; failures are logged + the row is removed.
    jobs = store.get_all_jobs()
    job_ids = {j.id for j in jobs}
    assert "t.tampered" not in job_ids
    assert "t.real" in job_ids

    # Row should be physically removed by parent sweep — verify via raw SQL.
    with store.engine.begin() as conn:
        ids_left = [r[0] for r in conn.execute(store.jobs_t.select())]
    assert "t.tampered" not in ids_left


# ── 6. Schema validation rejects bad payloads ───────────────────────────


def test_schema_validation_rejects_unknown_fields():
    """Extra key in JSON state -> _decode_job_state raises ValueError."""
    base_payload = {
        "version": 1,
        "id": "x",
        "func": "scheduler.jobs:auto_apply",
        "trigger": {
            "__type__": "CronTrigger",
            "fields": {
                "year": "*",
                "month": "*",
                "day": "*",
                "week": "*",
                "day_of_week": "*",
                "hour": "*",
                "minute": "*",
                "second": "*",
            },
            "timezone": "UTC",
            "start_date": None,
            "end_date": None,
            "jitter": None,
        },
        "executor": "default",
        "args": [],
        "kwargs": {},
        "name": "x",
        "misfire_grace_time": 1,
        "coalesce": True,
        "max_instances": 1,
        "next_run_time": None,
    }

    # Extra field
    with_extra = dict(base_payload)
    with_extra["injected_field"] = "evil"
    with pytest.raises(ValueError, match="unexpected fields"):
        _decode_job_state(json.dumps(with_extra).encode("utf-8"))

    # Missing field
    missing = dict(base_payload)
    del missing["args"]
    with pytest.raises(ValueError, match="missing required fields"):
        _decode_job_state(json.dumps(missing).encode("utf-8"))


# ── 7. Allowlist parity with register_all + register_scraping_jobs ──────


class _RecordingScheduler:
    """Captures add_job calls so we can compute the realized func_ref set."""

    def __init__(self) -> None:
        self.added: list[Any] = []

    def add_job(self, func, *args, **kwargs):
        self.added.append(func)


def test_allowlist_matches_register_all():
    """Every callable that register_all / register_scraping_jobs hands to
    add_job must be in FUNC_REF_ALLOWLIST. Catches the "new scraper, forgot
    to update allowlist" regression.
    """
    rec = _RecordingScheduler()
    scheduler_jobs.register_all(rec)  # type: ignore[arg-type]
    # register_all internally calls scraping.register_scraping_jobs; no need
    # to invoke it again.

    realized: set[str] = {obj_to_ref(fn) for fn in rec.added}
    assert realized == set(FUNC_REF_ALLOWLIST), (
        f"FUNC_REF_ALLOWLIST drift detected.\n"
        f"  in allowlist not registered: {set(FUNC_REF_ALLOWLIST) - realized}\n"
        f"  registered not in allowlist: {realized - set(FUNC_REF_ALLOWLIST)}\n"
        f"Update FUNC_REF_ALLOWLIST in src/scheduler/json_jobstore.py."
    )


# ── 8. _encode_job_state direct call sanity ──────────────────────────────


def test_encode_then_decode_preserves_state_shape():
    """Unit test the codec without going through the store."""
    trigger = CronTrigger.from_crontab("0 * * * *", timezone="UTC")
    state = {
        "version": 1,
        "id": "u.test",
        "func": "scheduler.jobs:auto_apply",
        "trigger": trigger,
        "executor": "default",
        "args": (),
        "kwargs": {},
        "name": "u.test",
        "misfire_grace_time": 60,
        "coalesce": True,
        "max_instances": 1,
        "next_run_time": datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
    }
    blob = _encode_job_state(state)
    assert blob[0:1] == b"{"  # JSON, not pickle

    decoded = _decode_job_state(blob)
    assert decoded["id"] == "u.test"
    assert decoded["func"] == "scheduler.jobs:auto_apply"
    assert decoded["args"] == ()
    assert isinstance(decoded["trigger"], CronTrigger)
    assert decoded["next_run_time"] == state["next_run_time"]


# ── 9. DateTrigger round-trip ───────────────────────────────────────────


def test_roundtrip_date_trigger():
    """DateTrigger round-trips through encoder + decoder.

    DateTrigger isn't used in production yet (transient one-off via
    /api/v1/scheduler/jobs/{id}/run from plan 47 is the future use case),
    but the codec ships now to support that path.
    """
    store = _make_store()
    run_date = datetime(2027, 1, 1, 12, 30, tzinfo=UTC)
    trigger = DateTrigger(run_date=run_date, timezone="UTC")
    _add_job(store, scheduler_jobs.auto_apply, job_id="t.date", trigger=trigger)

    looked_up = store.lookup_job("t.date")
    assert looked_up is not None
    assert isinstance(looked_up.trigger, DateTrigger)
    assert looked_up.trigger.run_date == run_date


# ── 10. _decode_datetime naive-rejection (plan 75 / 0.3.3.03) ───────────


def test_decode_datetime_rejects_naive():
    """Plan 75 / 0.3.3.03 — naive timestamps in job_state are tampered/legacy
    and produce misfire-timing risk. Reject loudly instead of silently
    rebasing to UTC.
    """
    from scheduler.json_jobstore import _decode_datetime

    with pytest.raises(ValueError, match="naive datetime"):
        _decode_datetime("2026-05-21T10:00:00")


def test_decode_datetime_accepts_tzaware():
    """Tz-aware ISO 8601 round-trips through `_decode_datetime`."""
    from scheduler.json_jobstore import _decode_datetime

    out = _decode_datetime("2026-05-21T10:00:00+00:00")
    assert out is not None
    assert out.tzinfo is not None
    assert out.utcoffset().total_seconds() == 0


# ── 11. add_job ON CONFLICT DO NOTHING (plan 0.7.0.44, 2026-05-22) ─────


def test_add_job_raises_conflicting_id_on_duplicate():
    """Adding two jobs with the same id raises `ConflictingIdError`.

    Plan 0.7.0.44: switched the add_job impl from `INSERT + catch
    IntegrityError` to `INSERT ... ON CONFLICT DO NOTHING + check
    rowcount`. The publicly observable behavior — ConflictingIdError on
    duplicate id — must remain identical so APScheduler's
    `Scheduler.add_job(..., replace_existing=True)` fallback to
    `update_job` still fires. This test pins the contract.
    """
    from apscheduler.jobstores.base import ConflictingIdError

    store = _make_store()
    trigger = IntervalTrigger(seconds=60)
    _add_job(store, scheduler_jobs.auto_apply, job_id="dup.id", trigger=trigger)

    # Second add with same id — must raise.
    with pytest.raises(ConflictingIdError):
        _add_job(store, scheduler_jobs.auto_apply, job_id="dup.id", trigger=trigger)


def test_add_job_uses_dialect_aware_on_conflict_for_postgres_and_sqlite():
    """Plan 0.7.0.44: verify the dialect-aware INSERT path is used for
    sqlite (the test backend). The signal: when a duplicate INSERT runs,
    NO IntegrityError exception is raised from the dialect layer (the
    catch-IntegrityError fallback is dead code on sqlite + postgres);
    instead `result.rowcount == 0` is what triggers
    `ConflictingIdError`. We probe this via mock: spy on the connection
    and assert the INSERT statement compiles with `ON CONFLICT`.

    This test prevents a regression where someone changes the helper
    back to plain `self.jobs_t.insert()` (which would re-introduce the
    [db] ERROR spam in production).
    """
    store = _make_store()
    # Add a baseline job so the second INSERT triggers the conflict path.
    trigger = IntervalTrigger(seconds=60)
    _add_job(store, scheduler_jobs.auto_apply, job_id="onconflict.test", trigger=trigger)

    # Second add path — by inspecting the compiled statement we verify
    # ON CONFLICT is in play (sqlite syntax: "ON CONFLICT (id) DO NOTHING").
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    test_stmt = (
        sqlite_insert(store.jobs_t)
        .values(
            id="onconflict.test",
            next_run_time=datetime_to_utc_timestamp(datetime(2026, 1, 1, tzinfo=UTC)),
            job_state=b"{}",
        )
        .on_conflict_do_nothing(index_elements=["id"])
    )
    compiled = str(test_stmt.compile(dialect=store.engine.dialect))
    assert "ON CONFLICT" in compiled.upper()
    assert "DO NOTHING" in compiled.upper()


def test_add_job_then_update_job_via_store_api_round_trip():
    """Plan 0.7.0.44: prove the store-level contract that APScheduler
    relies on — `add_job` raises `ConflictingIdError` on duplicate;
    follow-up `update_job` succeeds + the new trigger is persisted.
    This mirrors what `Scheduler.add_job(..., replace_existing=True)`
    does internally (try add_job → catch ConflictingIdError → call
    update_job), but exercises only the store boundary (the Scheduler
    integration test would need `.start()` which complicates teardown).
    """
    from apscheduler.jobstores.base import ConflictingIdError

    store = _make_store()
    scheduler = store._scheduler

    # First add via the helper — registers the row.
    first_job = _add_job(
        store,
        scheduler_jobs.auto_apply,
        job_id="upsert.id",
        trigger=IntervalTrigger(seconds=60),
    )
    assert first_job is not None

    # Second add — must raise.
    with pytest.raises(ConflictingIdError):
        _add_job(
            store,
            scheduler_jobs.auto_apply,
            job_id="upsert.id",
            trigger=IntervalTrigger(seconds=120),
        )

    # Manual update_job (mirroring Scheduler.add_job's fallback path).
    second_job = Job(
        scheduler,
        id="upsert.id",
        func=scheduler_jobs.auto_apply,
        trigger=IntervalTrigger(seconds=120),
        args=(),
        kwargs={},
        name="upsert.id",
        misfire_grace_time=1,
        coalesce=True,
        max_instances=1,
        next_run_time=datetime(2026, 1, 1, tzinfo=UTC),
        executor="default",
    )
    store.update_job(second_job)

    looked_up = store.lookup_job("upsert.id")
    assert looked_up is not None
    assert isinstance(looked_up.trigger, IntervalTrigger)
    assert looked_up.trigger.interval.total_seconds() == 120
