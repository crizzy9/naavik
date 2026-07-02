"""HTMX fragment routes — modals + cross-cutting partials.

Plan 08 shipped `/_modal/confirm`. Plan 09 adds:
- GET /_modal/bullet-editor/{bullet_id}      — bullet editor modal (Section 6)
- GET /_fragments/onboarding/step/{n}        — onboarding step partial (Section 2)
- GET /_fragments/profile/bullet-row/{id}    — single bullet row reload
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from db.session import get_session
from models import User
from services import profile_service
from services.auth import require_authed_session
from ui import profile_ctx as pctx
from ui.templates_setup import templates

router = APIRouter()

# Sources shown on the scrape-status strip, with short labels.
_STRIP_SOURCE_LABELS = {
    "linkedin": "LinkedIn",
    "indeed": "Indeed",
    "workday": "Workday",
    "greenhouse": "Greenhouse",
    "lever": "Lever",
    "ashby": "Ashby",
}


@router.get("/_fragments/scrape-status", response_class=HTMLResponse, name="scrape_status")
async def get_scrape_status(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    """Live scrape-run status strip — queued → running → found N → done/failed.

    Queued = a transient `scraping.<source>-manual-*` APScheduler job exists
    but its JobScrapeRun row hasn't been opened yet. Running/finished rows
    come from JobScrapeRun (last 15 minutes). Polls itself every 3s while
    anything is active (docs/design/JOB_SEARCH_PREFERENCES.md § G).
    """
    from datetime import UTC, datetime, timedelta

    from services import job_service
    from ui.routes.profile import _effective_user_id
    from ui.routes.settings import _format_started_at

    user_id = _effective_user_id(user)
    rows = await job_service.list_recent_scrape_runs(session, user_id=user_id, limit=12)
    cutoff = datetime.now(UTC) - timedelta(minutes=15)

    runs: list[dict] = []
    running_sources: set[str] = set()
    for run in rows:
        started = run.started_at
        if started is not None and started.tzinfo is None:
            started = started.replace(tzinfo=UTC)
        is_running = run.status.value == "running"
        if not is_running and (started is None or started < cutoff):
            continue
        if is_running:
            running_sources.add(run.source.value)
        runs.append(
            {
                "source_label": _STRIP_SOURCE_LABELS.get(run.source.value, run.source.value),
                "status": run.status.value,
                "new_jobs": run.new_jobs or 0,
                "listings": run.listings_returned or 0,
                "started_label": _format_started_at(run.started_at),
                "error": (run.errors or [None])[0],
            }
        )

    # Queued = accepted manual trigger with no RUNNING row yet.
    queued: list[dict] = []
    try:
        from scheduler import get_scheduler

        sched = get_scheduler()
        if sched is not None:
            for job in sched.get_jobs():
                parts = job.id.split("-manual-")
                if len(parts) == 2 and parts[0].startswith("scraping."):
                    source_value = parts[0].removeprefix("scraping.")
                    if source_value not in running_sources:
                        queued.append(
                            {
                                "source_label": _STRIP_SOURCE_LABELS.get(
                                    source_value, source_value
                                ),
                                "status": "queued",
                                "new_jobs": 0,
                                "listings": 0,
                                "started_label": "",
                                "error": None,
                            }
                        )
    except Exception:  # noqa: BLE001 — scheduler absent in some test contexts
        pass

    runs = queued + runs
    any_active = bool(queued) or bool(running_sources)
    return templates.TemplateResponse(
        request,
        "components/_scrape_status_strip.html",
        {"runs": runs[:6], "poll": any_active},
    )


@router.get("/_modal/confirm", response_class=HTMLResponse, name="modal_confirm")
async def confirm_modal(
    request: Request,
    title: str,
    message: str,
    action: str,
    label: str = "Confirm",
    tone: Literal["danger", "warning", "primary"] = "danger",
    method: Literal["post", "delete", "put", "patch"] = "post",
    cancel_label: str = "Cancel",
):
    return templates.TemplateResponse(
        request,
        "components/confirm_modal.html",
        {
            "title": title,
            "message": message,
            "confirm_action_url": action,
            "confirm_label": label,
            "confirm_tone": tone,
            "confirm_method": method,
            "cancel_label": cancel_label,
        },
    )


@router.get(
    "/_modal/bullet-editor/{bullet_id}",
    response_class=HTMLResponse,
    name="modal_bullet_editor",
)
async def bullet_editor_modal(
    request: Request,
    bullet_id: int,
    session: AsyncSession = Depends(get_session),
):
    bullet = await profile_service.get_bullet(session, bullet_id)
    if bullet is None:
        raise HTTPException(status_code=404, detail="Bullet not found")
    exp = await profile_service.get_experience(session, bullet.experience_id)
    role_label = f"{exp.company} · {exp.title}" if exp else "Bullet"
    return templates.TemplateResponse(
        request,
        "components/bullet_editor_modal.html",
        {
            "bullet": pctx.bullet_dict(bullet),
            "role_label": role_label,
        },
    )


@router.get(
    "/_fragments/profile/bullet-row/{bullet_id}",
    response_class=HTMLResponse,
    name="profile_bullet_row",
)
async def profile_bullet_row(
    request: Request,
    bullet_id: int,
    session: AsyncSession = Depends(get_session),
):
    bullet = await profile_service.get_bullet(session, bullet_id)
    if bullet is None:
        raise HTTPException(status_code=404, detail="Bullet not found")
    return templates.TemplateResponse(
        request,
        "components/bullet_edit_row.html",
        {"bullet": pctx.bullet_dict(bullet)},
    )


@router.get(
    "/_fragments/onboarding/step/{step}",
    response_class=HTMLResponse,
    name="onboarding_step_fragment",
)
async def onboarding_step(request: Request, step: int):
    # Plan 0.7.0.48 Wave 2 (2026-05-25): onboarding collapsed to a single
    # upload step. The legacy SSE-extracting + review partials are deleted.
    if step != 1:
        raise HTTPException(status_code=404, detail="Unknown step")
    return templates.TemplateResponse(
        request,
        "pages/_onboarding_step_upload.html",
        {},
    )
