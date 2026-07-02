"""Background bundle-generation dispatch.

A GET must never block on LLM + Typst. Routes mark the application
`docs_state=GENERATING`, commit, then call `spawn_generation` — the bundle
runs in an asyncio task with its own DB session while the workspace polls
`/_fragments/discover/workspace/{job_id}` until the state settles.

State contract:
- GENERATING is set (and committed) by the caller BEFORE spawning, so the
  first paint already shows the generating indicator.
- On success `bundle_generator` flips docs_state to READY (via
  `generate_resume`); on any exception this module flips it to FAILED and
  records `submission_artifacts.generation_error` for the retry surface.
- A GENERATING row older than `STALE_GENERATING_AFTER` is treated as FAILED
  by the UI (process restarts orphan in-flight tasks).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlmodel import select

from models import Application, DocsState, Settings

log = logging.getLogger(__name__)

STALE_GENERATING_AFTER = timedelta(minutes=5)

# Keep strong references so in-flight tasks aren't garbage-collected, and so
# double-clicks / poll races can't start a second generation for the same app.
_tasks: dict[int, asyncio.Task] = {}

# Kill-switch for tests — the spawned task opens its own `db.session.
# async_session`, which test fixtures don't override. `tests/conftest.py`
# flips this off autouse so route tests never leak real-DB writes.
enabled: bool = True


def is_generation_stale(application: Application) -> bool:
    """A GENERATING application nobody is working on (e.g. after a restart)."""
    if application.docs_state != DocsState.GENERATING:
        return False
    updated = application.updated_at
    if updated is None:
        return True
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=UTC)
    return datetime.now(UTC) - updated > STALE_GENERATING_AFTER


async def mark_generating(session, application: Application) -> None:
    """Flip docs_state → GENERATING in the caller's session (caller commits)."""
    application.docs_state = DocsState.GENERATING
    application.updated_at = datetime.now(UTC)
    session.add(application)
    await session.flush()


def spawn_generation(application_id: int) -> bool:
    """Start bundle generation for `application_id` in the background.

    Returns False when a generation task is already in flight for this
    application (the caller keeps polling the existing one).
    """
    if not enabled:
        return False
    existing = _tasks.get(application_id)
    if existing is not None and not existing.done():
        return False
    task = asyncio.get_running_loop().create_task(
        _run_generation(application_id),
        name=f"bundle-generation-{application_id}",
    )
    _tasks[application_id] = task
    task.add_done_callback(
        lambda t: _tasks.pop(application_id, None) if _tasks.get(application_id) is t else None
    )
    return True


async def _run_generation(application_id: int) -> None:
    """Own-session bundle generation; never raises."""
    from db.session import async_session
    from services.bundle_generator import generate_bundle

    try:
        async with async_session() as session:
            application = (
                await session.exec(select(Application).where(Application.id == application_id))
            ).one_or_none()
            if application is None:
                return
            settings = (
                await session.exec(select(Settings).where(Settings.user_id == application.user_id))
            ).one_or_none()
            if settings is None:
                settings = Settings(user_id=application.user_id)
            try:
                result = await generate_bundle(session, application, settings=settings)
                if result.skipped_reason:
                    # Bailed before generating anything (e.g. cost cap) — the
                    # app must not sit in GENERATING forever.
                    application.docs_state = DocsState.FAILED
                    _record_error(application, result.skipped_reason)
                    session.add(application)
                await session.commit()
                log.info(
                    "background generation finished app=%s docs_state=%s degraded=%s",
                    application_id,
                    application.docs_state.value,
                    result.degraded,
                )
            except Exception as exc:  # noqa: BLE001 — background task must not crash the loop
                await session.rollback()
                application = (
                    await session.exec(select(Application).where(Application.id == application_id))
                ).one_or_none()
                if application is not None:
                    application.docs_state = DocsState.FAILED
                    _record_error(application, str(exc)[:500])
                    application.updated_at = datetime.now(UTC)
                    session.add(application)
                    await session.commit()
                log.warning("background generation failed app=%s: %s", application_id, exc)
    except Exception as exc:  # noqa: BLE001
        log.error("background generation crashed app=%s: %s", application_id, exc)


def _record_error(application: Application, message: str) -> None:
    artifacts = dict(application.submission_artifacts or {})
    artifacts["generation_error"] = {
        "message": message,
        "at": datetime.now(UTC).isoformat(),
    }
    application.submission_artifacts = artifacts
