"""Operator scheduler endpoints — `GET / POST /api/v1/scheduler/jobs[/...]`.

Plan 47 (0.2.0.10a). Operator-facing read + control plane over the lifespan-
managed APScheduler registered crons (see `src/scheduler/__init__.py`).
Until the `0.2.5.04` scraper-run history UI ships, this is the only path to
confirm cron registration, trigger an out-of-band re-run, or pause/resume a
misbehaving scraper without restarting the app or editing Postgres directly.

One-off run = transient `add_job(DateTrigger(now), id="<orig>-manual-<uuid8>")`
per plan § D.1 Option B — preserves the original cron's `next_run_time`,
which is the operator's contract surface.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from apscheduler.jobstores.base import JobLookupError
from apscheduler.triggers.date import DateTrigger
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api.auth import require_csrf
from models import User
from scheduler import get_scheduler
from services.auth import require_authed_session

router = APIRouter(prefix="/api/v1/scheduler")


# ── Response models ─────────────────────────────────────────────────────


class SchedulerJobInfo(BaseModel):
    id: str
    name: str
    next_run_time: datetime | None
    trigger: str
    max_instances: int
    coalesce: bool
    paused: bool
    pending: bool


class SchedulerJobList(BaseModel):
    running: bool
    jobs: list[SchedulerJobInfo]


class ScheduledRunResponse(BaseModel):
    queued_job_id: str
    scheduled_at: datetime


# ── Helpers ─────────────────────────────────────────────────────────────


def _require_running_scheduler():
    """Return the live scheduler or 503 if not started.

    The lifespan boots scheduler before the first request per FastAPI
    semantics, but `_SCHEDULER` is None on cold-start race / boot edge cases
    (e.g. tests that skip lifespan). Caller maps None → 503.
    """
    scheduler = get_scheduler()
    if scheduler is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="scheduler not started",
        )
    return scheduler


def _job_to_info(job) -> SchedulerJobInfo:
    """Materialize an APScheduler `Job` into the response shape."""
    return SchedulerJobInfo(
        id=job.id,
        name=job.name,
        next_run_time=job.next_run_time,
        trigger=str(job.trigger),
        max_instances=job.max_instances,
        coalesce=job.coalesce,
        paused=job.next_run_time is None,
        pending=job.pending,
    )


# ── Endpoints ───────────────────────────────────────────────────────────


@router.get("/jobs", name="api_scheduler_jobs_list")
async def list_jobs(
    _user: User | None = Depends(require_authed_session),
) -> SchedulerJobList:
    scheduler = _require_running_scheduler()
    jobs = [_job_to_info(j) for j in scheduler.get_jobs()]
    return SchedulerJobList(running=bool(scheduler.running), jobs=jobs)


@router.post(
    "/jobs/{job_id}/run",
    name="api_scheduler_jobs_run",
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_job_now(
    job_id: str,
    _user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
) -> ScheduledRunResponse:
    """Trigger a one-off NOW run of a registered job.

    Adds a transient `add_job(DateTrigger(now))` whose id is
    `<job_id>-manual-<uuid8>`. The original cron's `next_run_time` is NOT
    mutated — `coalesce=True` + `max_instances=1` on the original protect
    it from racing with itself; the manual id is distinct so APScheduler
    treats it as a separate registration.
    """
    scheduler = _require_running_scheduler()
    try:
        job = scheduler.get_job(job_id)
    except JobLookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"job {job_id} not found",
        ) from exc
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"job {job_id} not found",
        )

    now = datetime.now(UTC)
    manual_id = f"{job_id}-manual-{uuid4().hex[:8]}"
    scheduler.add_job(
        job.func,
        DateTrigger(run_date=now),
        id=manual_id,
        name=manual_id,
        args=[],
        kwargs={},
        max_instances=1,
        coalesce=True,
        replace_existing=False,
    )
    return ScheduledRunResponse(queued_job_id=manual_id, scheduled_at=now)


@router.post("/jobs/{job_id}/pause", name="api_scheduler_jobs_pause")
async def pause_job(
    job_id: str,
    _user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
) -> SchedulerJobInfo:
    scheduler = _require_running_scheduler()
    try:
        scheduler.pause_job(job_id)
        job = scheduler.get_job(job_id)
    except JobLookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"job {job_id} not found",
        ) from exc
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"job {job_id} not found",
        )
    return _job_to_info(job)


@router.post("/jobs/{job_id}/resume", name="api_scheduler_jobs_resume")
async def resume_job(
    job_id: str,
    _user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
) -> SchedulerJobInfo:
    scheduler = _require_running_scheduler()
    try:
        scheduler.resume_job(job_id)
        job = scheduler.get_job(job_id)
    except JobLookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"job {job_id} not found",
        ) from exc
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"job {job_id} not found",
        )
    return _job_to_info(job)


__all__ = [
    "ScheduledRunResponse",
    "SchedulerJobInfo",
    "SchedulerJobList",
    "router",
]
