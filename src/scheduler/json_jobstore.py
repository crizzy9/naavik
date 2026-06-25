"""JSON-serializing variant of APScheduler's SQLAlchemyJobStore.

Per docs/plans/48-0.2.0.10b-pickle-deser-replacement.md § D.1. Replaces
pickle deserialization in `_reconstitute_job` to close the
RCE-on-DB-compromise vector flagged in PR #109 hacker review (#111).

Compatibility scope: handles CronTrigger, IntervalTrigger, DateTrigger
(every trigger Naavik uses per src/scheduler/jobs.py + scraping.py).
Other triggers raise `UnsupportedTriggerError` at add_job time — fail
fast at write rather than silently corrupt persistence.

Defense-in-depth: func references on load are validated against an
explicit allowlist (`FUNC_REF_ALLOWLIST`). A tampered row pointing at
e.g. `os:system` is rejected and removed, matching the existing "unable
to restore -> remove" pattern at parent `_get_jobs:174-189`.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from apscheduler.job import Job
from apscheduler.jobstores.base import ConflictingIdError, JobLookupError
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.base import BaseTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.util import datetime_to_utc_timestamp
from sqlalchemy.exc import IntegrityError

log = logging.getLogger(__name__)


class UnsupportedTriggerError(TypeError):
    """Raised when add_job receives a trigger without a JSON codec."""


# Allowlist of every callable that may be deserialized on scheduler boot.
# Form: "module:qualname" per apscheduler.util.obj_to_ref. New scheduled
# job = append a line here; CI's `tests/test_json_jobstore.py::
# test_allowlist_matches_register_all` enforces parity with
# `scheduler.jobs.register_all` + `scheduler.scraping.register_scraping_jobs`.
FUNC_REF_ALLOWLIST: frozenset[str] = frozenset(
    {
        # src/scheduler/jobs.py
        "scheduler.jobs:auto_apply",
        "scheduler.jobs:aggregate_costs",
        "scheduler.jobs:cleanup_revoked_jwts",
        "scheduler.jobs:cleanup_stale_docs",
        "scheduler.jobs:cleanup_stale_drafts",
        "scheduler.jobs:daily_db_snapshot",
        # Plan 61 (0.2.7.16): semantic-match nightly batch + orphan sweep.
        "scheduler.jobs:embed_pending_jobs",
        "scheduler.jobs:embed_orphan_sweep",
        # Plan 65 (0.3.0.03): profile-embedding nightly batch.
        "scheduler.jobs:embed_pending_profiles",
        # Plan 65 (0.3.0.06): score-pending + recompute-stale crons.
        "scheduler.jobs:score_pending",
        "scheduler.jobs:score_recompute_stale",
        # Plan 73 (0.3.2.03): per-role-family score trend rollup.
        "scheduler.jobs:score_aggregate_daily",
        # Plan 62 (0.2.7.07): RETIRING signing-key sweep.
        "scheduler.jobs:expire_retiring_signing_keys",
        "scheduler.jobs:refresh_oauth_tokens",
        # Plan 90 (0.5.0.01 + 0.5.0.02): email sync + classify crons.
        "scheduler.jobs:sync_emails",
        "scheduler.jobs:classify_emails",
        # src/scheduler/scraping.py
        "scheduler.scraping:scrape_linkedin",
        "scheduler.scraping:scrape_workday",
        "scheduler.scraping:scrape_greenhouse",
        "scheduler.scraping:scrape_lever",
        "scheduler.scraping:scrape_ashby",
        "scheduler.scraping:scrape_indeed",
    }
)


# ── Trigger codec ────────────────────────────────────────────────────────


def _encode_trigger(trigger: BaseTrigger) -> dict[str, Any]:
    """Encode a supported trigger to a JSON dict via class-tagged init args."""
    if isinstance(trigger, CronTrigger):
        # CronTrigger.fields is list[BaseField]; str(field) round-trips through
        # the constructor's per-field kwarg.
        field_kwargs = {field.name: str(field) for field in trigger.fields}
        return {
            "__type__": "CronTrigger",
            "fields": field_kwargs,
            "timezone": str(trigger.timezone) if trigger.timezone else None,
            "start_date": _encode_datetime(trigger.start_date),
            "end_date": _encode_datetime(trigger.end_date),
            "jitter": trigger.jitter,
        }
    if isinstance(trigger, IntervalTrigger):
        return {
            "__type__": "IntervalTrigger",
            "seconds": trigger.interval.total_seconds(),
            "timezone": str(trigger.timezone) if trigger.timezone else None,
            "start_date": _encode_datetime(trigger.start_date),
            "end_date": _encode_datetime(trigger.end_date),
            "jitter": trigger.jitter,
        }
    if isinstance(trigger, DateTrigger):
        return {
            "__type__": "DateTrigger",
            "run_date": _encode_datetime(trigger.run_date),
            "timezone": str(trigger.run_date.tzinfo)
            if trigger.run_date and trigger.run_date.tzinfo
            else None,
        }
    raise UnsupportedTriggerError(
        f"Trigger type {type(trigger).__name__} has no JSON codec; "
        "add a branch to _encode_trigger + _decode_trigger in json_jobstore.py."
    )


def _decode_trigger(d: dict[str, Any]) -> BaseTrigger:
    kind = d.get("__type__")
    if kind == "CronTrigger":
        return CronTrigger(
            **d["fields"],
            timezone=d.get("timezone"),
            start_date=_decode_datetime(d.get("start_date")),
            end_date=_decode_datetime(d.get("end_date")),
            jitter=d.get("jitter"),
        )
    if kind == "IntervalTrigger":
        return IntervalTrigger(
            seconds=d["seconds"],
            timezone=d.get("timezone"),
            start_date=_decode_datetime(d.get("start_date")),
            end_date=_decode_datetime(d.get("end_date")),
            jitter=d.get("jitter"),
        )
    if kind == "DateTrigger":
        return DateTrigger(
            run_date=_decode_datetime(d.get("run_date")),
            timezone=d.get("timezone"),
        )
    raise UnsupportedTriggerError(f"Unknown trigger __type__={kind!r} in stored job_state")


def _encode_datetime(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


def _decode_datetime(s: str | None) -> datetime | None:
    if s is None:
        return None
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        # Plan 75 / 0.3.3.03 — reject naive timestamps. `_encode_datetime`
        # always writes `dt.isoformat()` on a tz-aware datetime; a naive
        # value here means tampered/legacy job_state and a misfire-timing
        # risk. Fail loud rather than silently rebase to UTC.
        raise ValueError(
            f"naive datetime {s!r} in job_state — tzinfo required; see plan 75 / 0.3.3.03 hardening"
        )
    return dt


# ── Job state codec ──────────────────────────────────────────────────────


_REQUIRED_FIELDS = frozenset(
    {
        "version",
        "id",
        "func",
        "trigger",
        "executor",
        "args",
        "kwargs",
        "name",
        "misfire_grace_time",
        "coalesce",
        "max_instances",
        "next_run_time",
    }
)


def _encode_job_state(state: dict[str, Any]) -> bytes:
    payload = {
        "version": state["version"],
        "id": state["id"],
        "func": state["func"],
        "trigger": _encode_trigger(state["trigger"]),
        "executor": state["executor"],
        "args": list(state["args"]),
        "kwargs": state["kwargs"],
        "name": state["name"],
        "misfire_grace_time": state["misfire_grace_time"],
        "coalesce": state["coalesce"],
        "max_instances": state["max_instances"],
        "next_run_time": _encode_datetime(state["next_run_time"]),
    }
    return json.dumps(payload, allow_nan=False).encode("utf-8")


def _decode_job_state(blob: bytes) -> dict[str, Any]:
    payload = json.loads(blob.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("job_state JSON is not an object")
    missing = _REQUIRED_FIELDS - set(payload.keys())
    if missing:
        raise ValueError(f"job_state missing required fields: {sorted(missing)}")
    extra = set(payload.keys()) - _REQUIRED_FIELDS
    if extra:
        raise ValueError(f"job_state has unexpected fields: {sorted(extra)}")
    if payload["func"] not in FUNC_REF_ALLOWLIST:
        raise ValueError(f"job_state func={payload['func']!r} not in FUNC_REF_ALLOWLIST")
    return {
        "version": payload["version"],
        "id": payload["id"],
        "func": payload["func"],
        "trigger": _decode_trigger(payload["trigger"]),
        "executor": payload["executor"],
        "args": tuple(payload["args"]),
        "kwargs": payload["kwargs"],
        "name": payload["name"],
        "misfire_grace_time": payload["misfire_grace_time"],
        "coalesce": payload["coalesce"],
        "max_instances": payload["max_instances"],
        "next_run_time": _decode_datetime(payload["next_run_time"]),
    }


# ── Store ────────────────────────────────────────────────────────────────


class NaavikJsonJobStore(SQLAlchemyJobStore):
    """SQLAlchemyJobStore with pickle deser replaced by JSON + func-ref allowlist.

    Method override surface: add_job, update_job, _reconstitute_job. Everything
    else inherits unchanged. The `pickle_protocol` constructor arg from parent
    is accepted but ignored (kept for signature compat).
    """

    def add_job(self, job: Job) -> None:
        """Insert a job row; raise `ConflictingIdError` on duplicate id.

        Plan 0.7.0.44 — 2026-05-22: use Postgres `INSERT ... ON CONFLICT
        DO NOTHING` instead of the bare `INSERT` + catch-IntegrityError
        pattern. The catch-IntegrityError approach was correct
        functionally (APScheduler's Scheduler.add_job falls back to
        `update_job` when `replace_existing=True`), but Postgres logs
        the conflicted INSERT as a server-side `ERROR: duplicate key
        value violates unique constraint` line before the Python side
        catches the exception. Result: every orchestrator boot spammed
        the `[db]` log channel with one ERROR per registered job
        (~16 noisy lines on a fresh boot). `ON CONFLICT DO NOTHING`
        suppresses both the ERROR log and the IntegrityError, leaving
        the row state unchanged when the id already exists; the
        `rowcount == 0` check below detects the no-op and raises
        ConflictingIdError so APScheduler's update_job fallback fires
        on `replace_existing=True` as before.

        sqlite fallback: in-memory sqlite (test path) supports the same
        `INSERT ... ON CONFLICT (id) DO NOTHING` syntax since SQLite
        3.24 (2018). SQLAlchemy's dialect-aware `insert(...).
        on_conflict_do_nothing(index_elements=['id'])` constructs the
        right SQL per dialect.
        """
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        try:
            blob = _encode_job_state(job.__getstate__())
        except (TypeError, ValueError, UnsupportedTriggerError) as exc:
            raise TypeError(f"Job {job.id!r} is not JSON-serializable: {exc}") from exc

        # Dialect-aware INSERT builder. Both Postgres + SQLite support
        # ON CONFLICT; other dialects (we don't ship any) fall through
        # to the legacy IntegrityError-catch path.
        dialect_name = self.engine.dialect.name
        if dialect_name == "postgresql":
            stmt = (
                pg_insert(self.jobs_t)
                .values(
                    id=job.id,
                    next_run_time=datetime_to_utc_timestamp(job.next_run_time),
                    job_state=blob,
                )
                .on_conflict_do_nothing(index_elements=["id"])
            )
        elif dialect_name == "sqlite":
            stmt = (
                sqlite_insert(self.jobs_t)
                .values(
                    id=job.id,
                    next_run_time=datetime_to_utc_timestamp(job.next_run_time),
                    job_state=blob,
                )
                .on_conflict_do_nothing(index_elements=["id"])
            )
        else:
            stmt = self.jobs_t.insert().values(
                id=job.id,
                next_run_time=datetime_to_utc_timestamp(job.next_run_time),
                job_state=blob,
            )

        with self.engine.begin() as connection:
            try:
                result = connection.execute(stmt)
            except IntegrityError as exc:
                # Defense-in-depth for the legacy fallback path
                # (non-postgres / non-sqlite dialects).
                raise ConflictingIdError(job.id) from exc
            # ON CONFLICT DO NOTHING returns rowcount == 0 when the row
            # already exists. Raise ConflictingIdError so APScheduler's
            # Scheduler.add_job falls back to update_job under
            # replace_existing=True (preserving the prior behavior).
            if result.rowcount == 0:
                raise ConflictingIdError(job.id)

    def update_job(self, job: Job) -> None:
        try:
            blob = _encode_job_state(job.__getstate__())
        except (TypeError, ValueError, UnsupportedTriggerError) as exc:
            raise TypeError(f"Job {job.id!r} is not JSON-serializable: {exc}") from exc
        update = (
            self.jobs_t.update()
            .values(
                next_run_time=datetime_to_utc_timestamp(job.next_run_time),
                job_state=blob,
            )
            .where(self.jobs_t.c.id == job.id)
        )
        with self.engine.begin() as connection:
            result = connection.execute(update)
            if result.rowcount == 0:
                raise JobLookupError(job.id)

    def _reconstitute_job(self, job_state: bytes) -> Job:
        state = _decode_job_state(job_state)
        state["jobstore"] = self
        job = Job.__new__(Job)
        job.__setstate__(state)
        job._scheduler = self._scheduler
        job._jobstore_alias = self._alias
        return job


__all__ = [
    "FUNC_REF_ALLOWLIST",
    "NaavikJsonJobStore",
    "UnsupportedTriggerError",
]
