"""APScheduler integration — lifespan-managed.

Per BACKEND.md § I + plan 10 § C.7. The scheduler is started on FastAPI
startup and stopped on shutdown. Jobs use a `SQLAlchemyJobStore` so they
survive process restarts. APScheduler uses the sync sqlalchemy URL (we
strip the `+asyncpg` driver suffix from `DATABASE_URL` for the job store).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

log = logging.getLogger(__name__)

_SCHEDULER = None  # type: ignore[var-annotated]  # set in start()


def _sync_database_url() -> str:
    from config import settings

    raw = settings.database_url
    # APScheduler's SQLAlchemyJobStore wants the sync driver. Strip async suffix.
    return raw.replace("postgresql+asyncpg://", "postgresql+psycopg://").replace(
        "postgresql+psycopg_async://", "postgresql+psycopg://"
    )


def get_scheduler():
    """Return the live AsyncIOScheduler (or None if not started)."""
    return _SCHEDULER


def is_running() -> bool:
    return _SCHEDULER is not None and _SCHEDULER.running


async def start() -> None:
    """Boot the scheduler + register Wave 6 jobs. Idempotent."""
    global _SCHEDULER  # noqa: PLW0603
    if _SCHEDULER is not None and _SCHEDULER.running:
        return

    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    from scheduler.json_jobstore import NaavikJsonJobStore

    jobstore_url = _sync_database_url()
    try:
        jobstores = {"default": NaavikJsonJobStore(url=jobstore_url)}
    except Exception as exc:  # noqa: BLE001 — DB might not be ready in tests
        log.warning("apscheduler db jobstore unavailable; using memory: %s", exc)
        jobstores = {}

    _SCHEDULER = AsyncIOScheduler(jobstores=jobstores, timezone="UTC")
    from . import jobs

    jobs.register_all(_SCHEDULER)

    try:
        _SCHEDULER.start()
        for j in _SCHEDULER.get_jobs():
            log.info("apscheduler registered: %s next=%s", j.id, j.next_run_time)
    except Exception as exc:  # noqa: BLE001
        log.warning("apscheduler start failed: %s", exc)


async def shutdown() -> None:
    global _SCHEDULER  # noqa: PLW0603
    if _SCHEDULER is None:
        return
    try:
        _SCHEDULER.shutdown(wait=False)
    except Exception as exc:  # noqa: BLE001
        log.warning("apscheduler shutdown errored: %s", exc)
    _SCHEDULER = None


@asynccontextmanager
async def lifespan_manager(app: FastAPI):
    """FastAPI lifespan integration. Use as `lifespan=lifespan_manager`."""
    await start()
    try:
        yield
    finally:
        await shutdown()


__all__ = [
    "get_scheduler",
    "is_running",
    "lifespan_manager",
    "shutdown",
    "start",
]
