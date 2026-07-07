"""Read-only Job detail page — `GET /jobs/{job_id}`.

Plan 36 (`0.2.0.11`, 2026-05-19) ships this surface distinct from the
existing `/discover/{job_id}` application workspace. `/discover/{id}` is
the tailor + apply bundle; `/jobs/{id}` is the raw read of a scraped Job
with its source / scrape-run metadata, no draft attached.

IDOR contract: cross-user requests return 404 (not 403). Hidden by
default — see `services.jobs.archive_job` for the same convention
on mutating ops (plan 36 fold-in of 0.7.0.15).
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from api.auth import require_csrf
from db.session import get_session
from models import (
    ApplicationBoard,
    ApplicationStatus,
    JobCreate,
    JobRead,
    JobScrapeRun,
    JobSource,
    RemotePolicy,
    User,
)
from models.enums import JobQueueState, StatusChangeTrigger
from services import jobs as job_service
from services.auth import require_authed_session
from ui import jobs_ctx
from ui.templates_setup import templates

log = logging.getLogger(__name__)

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
    from api.deps import owned_job_or_404

    return await owned_job_or_404(session, job_id, user_id)


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
    return templates.TemplateResponse(request, "pages/jobs/job_detail.html", ctx)


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
    return templates.TemplateResponse(request, "pages/jobs/_job_detail_body.html", ctx)


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
        "components/jobs/_manual_job_entry_modal.html",
        {},
    )


# Plan 95 § 3.7 — "Where does this stand?" vocabulary → effect.
_STAND_QUEUE_STATES = {
    "to_review": JobQueueState.UNSWIPED,
    "saved": JobQueueState.SAVED,
    "applied": JobQueueState.APPLIED,
    "recruiter_screen": JobQueueState.APPLIED,
    "onsite_loop": JobQueueState.APPLIED,
    "offer": JobQueueState.APPLIED,
}
_STAND_STATUSES = {
    "applied": ApplicationStatus.APPLIED,
    "recruiter_screen": ApplicationStatus.RECRUITER_SCREEN,
    "onsite_loop": ApplicationStatus.ONSITE_LOOP,
    "offer": ApplicationStatus.OFFER,
}

_STAND_OPTIONS = [
    ("to_review", "To review (default)"),
    ("saved", "Todo / saved"),
    ("applied", "Applied"),
    ("recruiter_screen", "Recruiter screen"),
    ("onsite_loop", "Interview stage"),
    ("offer", "Offer"),
]


async def _apply_stand(
    session: AsyncSession,
    *,
    user_id: int,
    job,
    stand: str,
    applied_at_raw: str,
) -> None:
    """Initial-state selection (§ 3.7): queue-state flip + mid-stage
    Application with the back-dated trail via the SAME helper as
    `processes.track_process` — the funnel sees one shape."""
    import contextlib
    from datetime import UTC, datetime

    from services import applications as applications_service

    if stand not in _STAND_QUEUE_STATES:
        raise HTTPException(status_code=422, detail=f"invalid stand: {stand}")
    target_queue = _STAND_QUEUE_STATES[stand]
    if target_queue != JobQueueState.UNSWIPED:
        await job_service.set_queue_state(session, job.id, user_id=user_id, state=target_queue)

    status = _STAND_STATUSES.get(stand)
    if status is None:
        return
    applied_at = datetime.now(UTC)
    if applied_at_raw.strip():
        # Bad date → today; the picker constrains this in practice.
        with contextlib.suppress(ValueError):
            applied_at = datetime.fromisoformat(applied_at_raw.strip()).replace(tzinfo=UTC)
    await applications_service.create_tracked_application(
        session,
        user_id=user_id,
        job=job,
        status=status,
        applied_at=applied_at,
        actor="manual_add",
        first_note="Added manually (back-filled)",
        stage_note="Stage set by you at add time",
        first_trigger=StatusChangeTrigger.MANUAL,
        stage_trigger=StatusChangeTrigger.MANUAL,
    )


@router.post("/api/v1/jobs/manual/parse", response_class=HTMLResponse, name="jobs_manual_parse")
async def post_job_manual_parse(
    request: Request,
    url: Annotated[str, Form(min_length=8, max_length=2000)],
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    """URL → editable preview (plan 95 § 3.7 B). SSRF-guarded; NOTHING
    persists here — the human confirms (or corrects) first."""
    from services.jobs.add_by_url import AddByUrlError, parse_posting

    ctx: dict[str, object] = {"stand_options": _STAND_OPTIONS}
    try:
        parsed = await parse_posting(session, user_id=_effective_user_id(user), url=url.strip())
    except AddByUrlError as exc:
        ctx["parse_error"] = str(exc)
        return templates.TemplateResponse(request, "components/jobs/_manual_job_preview.html", ctx)
    except Exception as exc:  # noqa: BLE001 — degrade in-fragment, never a 500
        log.warning("manual parse failed for %r: %s", url, exc)
        ctx["parse_error"] = "Something went wrong fetching that URL — type the fields instead."
        return templates.TemplateResponse(request, "components/jobs/_manual_job_preview.html", ctx)
    await session.commit()  # ApiUsage row from the extraction call
    ctx["parsed"] = {
        "url": parsed.url,
        "company": parsed.company,
        "role": parsed.role,
        "location": parsed.location,
        "description": parsed.description,
        "salary_min": parsed.salary_min,
        "salary_max": parsed.salary_max,
        "board": parsed.board,
    }
    return templates.TemplateResponse(request, "components/jobs/_manual_job_preview.html", ctx)


@router.post("/api/v1/jobs/manual/confirm", name="jobs_manual_confirm")
async def post_job_manual_confirm(
    company: Annotated[str, Form()],
    role: Annotated[str, Form()],
    description: Annotated[str, Form()],
    url: Annotated[str, Form()],
    location: Annotated[str | None, Form()] = None,
    stand: Annotated[str, Form()] = "to_review",
    applied_at: Annotated[str, Form()] = "",
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    """Confirm the parsed preview (§ 3.7): persist the Job + initial state."""
    if not (company.strip() and role.strip() and description.strip()):
        raise HTTPException(status_code=422, detail="company, role, description required")
    try:
        payload = JobCreate(
            company=company.strip(),
            role=role.strip(),
            description=description.strip(),
            url=url.strip() or f"manual://entry/{uuid.uuid4().hex[:12]}",
            location=(location or "").strip() or None,
            board=ApplicationBoard.MANUAL,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    user_id = _effective_user_id(user)
    job = await job_service.create_manual_job(session, payload, user_id=user_id)
    await _apply_stand(session, user_id=user_id, job=job, stand=stand, applied_at_raw=applied_at)
    await session.commit()
    response = Response(status_code=204)
    response.headers["HX-Redirect"] = "/tracking"
    return response


@router.post("/api/v1/jobs/manual", name="jobs_manual")
async def post_job_manual(
    company: Annotated[str, Form()],
    role: Annotated[str, Form()],
    description: Annotated[str, Form()],
    url: Annotated[str | None, Form()] = None,
    location: Annotated[str | None, Form()] = None,
    source: Annotated[str, Form()] = "manual",
    remote_policy: Annotated[str, Form()] = "unknown",
    stand: Annotated[str, Form()] = "to_review",
    applied_at: Annotated[str, Form()] = "",
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    """Create a manually-entered Job (plan 53 § B.2; typed fallback in the
    plan 95 § 3.7 URL-first modal — same initial-state selection)."""
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

    user_id = _effective_user_id(user)
    job = await job_service.create_manual_job(session, payload, user_id=user_id)
    await _apply_stand(session, user_id=user_id, job=job, stand=stand, applied_at_raw=applied_at)
    await session.commit()
    response = Response(status_code=204)
    response.headers["HX-Redirect"] = "/tracking"
    return response


# ── Apply-target resolution affordances (job detail right rail) ──────────


async def _apply_target_card_response(request: Request, session: AsyncSession, job):
    ctx = await jobs_ctx.build_job_detail_ctx(session, job=job)
    return templates.TemplateResponse(
        request, "components/jobs/_apply_target_card.html", {"j": ctx["job"]}
    )


@router.post(
    "/api/v1/jobs/{job_id}/resolve-apply",
    response_class=HTMLResponse,
    name="jobs_resolve_apply",
)
async def post_job_resolve_apply(
    request: Request,
    job_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    """Re-run apply-target resolution for one job, inline.

    The verification affordance: runs the full ladder with a Tier-B budget of
    ONE authenticated fetch; the resolver's module-level auth lock serializes
    this against a concurrent cron sweep, so the LinkedIn politeness
    invariants hold. Can take up to ~a minute when the browser step runs.
    Returns the refreshed card fragment.
    """
    job = await _job_or_404(session, job_id, _effective_user_id(user))
    from services import applications, resolution
    from services.jobs import jd_enrichment

    auth = resolution.AuthContext(remaining=1) if resolution.auth_available() else None
    try:
        resolved = await resolution.resolve_job(job, auth=auth)
    except Exception as exc:  # noqa: BLE001 — surface as a counted failed attempt
        log.warning("inline apply-site resolution failed for job %s: %s", job.id, exc)
        resolution.note_failed_attempt(job)
    else:
        resolution.apply_resolution(job, resolved)
        if resolved.description_html or resolved.description_text:
            jd_enrichment.maybe_apply_discovered_description(job, resolved)
        await applications.resync_draft_apply_target(session, job)
    session.add(job)
    await session.commit()
    return await _apply_target_card_response(request, session, job)


@router.post(
    "/api/v1/jobs/{job_id}/apply-url",
    response_class=HTMLResponse,
    name="jobs_set_apply_url",
)
async def post_job_apply_url(
    request: Request,
    job_id: int,
    apply_url: Annotated[str, Form()],
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    """Operator-pasted apply target — the terminal escape hatch (via="manual").

    Normalized (wrapper unwrap + redirect follow) and classified like any
    resolved URL; a manual stamp never counts as a resolution attempt and is
    never overwritten by automation.
    """
    job = await _job_or_404(session, job_id, _effective_user_id(user))
    cleaned = (apply_url or "").strip()
    # Same navigability rule as models.job._validate_job_url, minus the
    # synthetic manual:// scheme — an apply target must be a real http(s) link.
    if not cleaned.lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail="Enter a full http(s) URL")

    from services import applications, resolution

    final, kind = await resolution.normalize_apply_url(cleaned)
    resolved = resolution.ResolvedApply(
        kind=kind or "company_site",
        apply_url=final,
        ats_org=resolution.ats_org_from_url(final, kind),
        via="manual",
        original_apply_url=cleaned if final != cleaned else None,
    )
    resolution.apply_resolution(job, resolved, count_attempt=False)
    await applications.resync_draft_apply_target(session, job)
    session.add(job)
    await session.commit()
    return await _apply_target_card_response(request, session, job)
