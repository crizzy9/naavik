"""Read-only Job detail page — `GET /jobs/{job_id}`.

Plan 36 (`0.2.0.11`, 2026-05-19) ships this surface distinct from the
existing `/discover/{job_id}` application workspace. `/discover/{id}` is
the tailor + apply bundle; `/jobs/{id}` is the raw read of a scraped Job
with its source / scrape-run metadata, no draft attached.

IDOR contract: cross-user requests return 404 (not 403). Hidden by
default — see `services.job_service.archive_job` for the same convention
on mutating ops (plan 36 fold-in of 0.7.0.15).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from api.auth import require_csrf
from db.session import get_session
from models import (
    ApplicationBoard,
    JobCreate,
    JobRead,
    JobScrapeRun,
    JobSource,
    RemotePolicy,
    User,
)
from services import job_service
from services.auth import require_authed_session
from ui import jobs_ctx
from ui.templates_setup import templates

router = APIRouter()


def _effective_user_id(user: User | None) -> int:
    """Resolve per-request user_id for IDOR scoping.

    Mirrors `ui.routes.discover._effective_user_id`: the fake-session
    transitional stub maps to the seeded owner user (id=1) per
    `db/sample_data.py:USER.id == 1` so /jobs/{id} still resolves for the
    test surrogate that pre-dates real auth. Real JWT sessions return
    `user.id`. Distinct from Discover's `_effective_user_id` (which returns
    None for fake-session to skip the live-DB pivot in `build_discover_ctx`)
    because /jobs/{id} is always a single-job lookup — no fallback path
    exists, so the seeded user surrogate is the right answer.
    """
    return user.id if user is not None else 1


async def _job_or_404(session: AsyncSession, job_id: int, user_id: int):
    """Fetch a Job and enforce the user-id boundary.

    Returns 404 (not 403) on cross-user access so the surface doesn't leak
    "job N belongs to a different user" — the IDOR mitigation pattern.
    """
    job = await job_service.get_job(session, job_id)
    if job is None or job.user_id != user_id or job.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


async def _last_scrape_run(session: AsyncSession, scrape_run_id: int | None) -> JobScrapeRun | None:
    if scrape_run_id is None:
        return None
    return await job_service.get_scrape_run(session, scrape_run_id)


@router.get("/jobs/{job_id}", response_class=HTMLResponse, name="job_detail")
async def get_job_detail(
    request: Request,
    job_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    job = await _job_or_404(session, job_id, _effective_user_id(user))
    scrape_run = await _last_scrape_run(session, job.last_scrape_run_id)
    ctx = await jobs_ctx.build_job_detail_ctx(session, job=job, scrape_run=scrape_run)
    ctx["active_sidebar"] = "jobs"
    ctx["active_template_path"] = "/jobs/:id"
    return templates.TemplateResponse(request, "pages/job_detail.html", ctx)


@router.get(
    "/_fragments/jobs/{job_id}",
    response_class=HTMLResponse,
    name="job_detail_fragment",
)
async def get_job_detail_fragment(
    request: Request,
    job_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    """HTMX-only fragment of the Job detail body (no chrome).

    Lets the Tracking list deep-link a Job preview into a drawer in a
    future row without a full page nav; today it returns the same body
    content as the page but without the base layout.
    """
    job = await _job_or_404(session, job_id, _effective_user_id(user))
    scrape_run = await _last_scrape_run(session, job.last_scrape_run_id)
    ctx = await jobs_ctx.build_job_detail_ctx(session, job=job, scrape_run=scrape_run)
    return templates.TemplateResponse(request, "pages/_job_detail_body.html", ctx)


@router.get("/api/v1/jobs/{job_id}", name="jobs_get")
async def get_job_json(
    job_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    """JSON read of a Job (moved here from `ui/routes/discover.py` per plan 36 § A).

    Enforces the same IDOR boundary as the HTML page. Projects through
    `JobRead` (not the raw SQLModel) so `raw_meta` JSONB does not leak via
    the public API surface (plan 46 / 0.2.0.11c hardening). Dates serialize
    ISO-8601 + enums emit `.value` strings via `model_dump(mode="json")`.
    """
    job = await _job_or_404(session, job_id, _effective_user_id(user))
    return JSONResponse(content=JobRead.model_validate(job).model_dump(mode="json"))


# ── Manual job entry modal + endpoint (plan 53 § B / 0.2.4.02) ───────────


@router.get("/_modal/manual-job", response_class=HTMLResponse, name="modal_manual_job")
async def manual_job_modal(request: Request):
    return templates.TemplateResponse(
        request,
        "components/_manual_job_entry_modal.html",
        {},
    )


@router.post("/api/v1/jobs/manual", name="jobs_manual")
async def post_job_manual(
    company: Annotated[str, Form()],
    role: Annotated[str, Form()],
    description: Annotated[str, Form()],
    url: Annotated[str | None, Form()] = None,
    location: Annotated[str | None, Form()] = None,
    source: Annotated[str, Form()] = "manual",
    remote_policy: Annotated[str, Form()] = "unknown",
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    """Create a manually-entered Job (plan 53 § B.2)."""
    if not (company.strip() and role.strip() and description.strip()):
        raise HTTPException(status_code=422, detail="company, role, description required")

    try:
        JobSource(source)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"invalid source: {source}") from exc

    try:
        payload = JobCreate(
            company=company.strip(),
            role=role.strip(),
            description=description.strip(),
            url=(url or "").strip() or f"manual://entry/{uuid.uuid4().hex[:12]}",
            location=(location or "").strip() or None,
            remote_policy=RemotePolicy(remote_policy),
            board=ApplicationBoard.MANUAL,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await job_service.create_manual_job(
        session,
        payload,
        user_id=_effective_user_id(user),
    )
    await session.commit()
    response = Response(status_code=204)
    response.headers["HX-Redirect"] = "/tracking"
    return response
