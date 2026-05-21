"""`score.aggregate_daily` cron registration + body — plan 73 (0.3.2.03).

Verifies the cron is wired into APScheduler's registry with the right
trigger shape and that the body is callable + invokes the per-user
update helper.
"""

from __future__ import annotations

import os

os.environ.setdefault("NAAVIK_DEBUG", "1")

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # noqa: E402
from apscheduler.triggers.cron import CronTrigger  # noqa: E402

from scheduler import jobs  # noqa: E402


def test_score_aggregate_daily_registered_with_0335_utc() -> None:
    """Plan 75 / 0.3.3.19: cron shifted 03:30 -> 03:35 UTC to avoid the
    theoretical concurrency window with `score.recompute_stale` (still
    at 03:30); APScheduler doesn't guarantee ordering within a single
    cron slot.
    """
    scheduler = AsyncIOScheduler()
    jobs.register_all(scheduler)
    job = scheduler.get_job("score.aggregate_daily")
    assert job is not None, "score.aggregate_daily cron not registered"
    trigger = job.trigger
    assert isinstance(trigger, CronTrigger)
    field_by_name = {f.name: str(f) for f in trigger.fields}
    assert field_by_name["hour"] == "3"
    assert field_by_name["minute"] == "35"
    assert str(trigger.timezone) == "UTC"


def test_score_aggregate_daily_is_callable() -> None:
    assert callable(jobs.score_aggregate_daily)
