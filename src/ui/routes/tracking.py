"""Tracking route + fragment + JSON stubs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Body, Form, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse

from db import sample_data as sd
from models.enums import ApplicationStatus, ClosedReason
from ui import tracking_ctx as tctx
from ui.templates_setup import templates

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────
# Page handler
# ─────────────────────────────────────────────────────────────────────────


@router.get("/tracking", response_class=HTMLResponse, name="tracking")
async def get_tracking(
    request: Request,
    view: Annotated[Literal["board", "list"], Query()] = "board",
    show_closed: Annotated[int, Query()] = 0,
):
    ctx = await tctx.build_tracking_ctx(view=view, show_closed=bool(show_closed))
    ctx["active_sidebar"] = "tracking"
    ctx["active_template_path"] = "/tracking"
    return templates.TemplateResponse(request, "pages/tracking.html", ctx)


# ─────────────────────────────────────────────────────────────────────────
# Fragment endpoints
# ─────────────────────────────────────────────────────────────────────────


@router.get(
    "/_fragments/tracking/board", response_class=HTMLResponse, name="tracking_board_fragment"
)
async def fragment_board(
    request: Request,
    show_closed: Annotated[int, Query()] = 0,
):
    ctx = await tctx.build_tracking_ctx(view="board", show_closed=bool(show_closed))
    return templates.TemplateResponse(request, "pages/_tracking_board.html", ctx)


@router.get("/_fragments/tracking/list", response_class=HTMLResponse, name="tracking_list_fragment")
async def fragment_list(request: Request):
    ctx = await tctx.build_tracking_ctx(view="list", show_closed=True)
    return templates.TemplateResponse(request, "pages/_tracking_list.html", ctx)


@router.get(
    "/_fragments/tracking/followup-banner",
    response_class=HTMLResponse,
    name="tracking_followup_fragment",
)
async def fragment_followup(request: Request):
    ctx = await tctx.build_tracking_ctx(view="board")
    if ctx["followup_count"] == 0:
        return HTMLResponse("")
    return templates.TemplateResponse(
        request,
        "components/followup_banner.html",
        {"count": ctx["followup_count"], "items": ctx["followup_items"]},
    )


# ─────────────────────────────────────────────────────────────────────────
# JSON stubs for application moves + manual entry + status overrides
# ─────────────────────────────────────────────────────────────────────────


@router.post("/api/v1/applications/move", name="applications_move")
async def post_application_move(
    request: Request,
    payload: Annotated[dict[str, Any] | None, Body()] = None,
    fail: Annotated[str | None, Query()] = None,
):
    if fail:
        raise HTTPException(status_code=502, detail="Couldn't move card")
    if not payload:
        return Response(status_code=204)
    app_id = int(payload.get("application_id", 0))
    target = payload.get("target_status")
    if app_id and target:
        try:
            await sd._apply_status_override(app_id, ApplicationStatus(target))
        except ValueError:
            raise HTTPException(status_code=422, detail="Bad status") from None
    return Response(status_code=204)


@router.post("/api/v1/applications/manual", name="applications_manual")
async def post_application_manual(
    request: Request,
    company: Annotated[str, Form()],
    role: Annotated[str, Form()],
    team: Annotated[str | None, Form()] = None,
    location: Annotated[str | None, Form()] = None,
    salary_min: Annotated[int | None, Form()] = None,
    salary_max: Annotated[int | None, Form()] = None,
    notes: Annotated[str | None, Form()] = None,
):
    await sd._append_manual_application(
        company=company,
        role=role,
        team=team,
        location=location,
        salary_min=salary_min,
        salary_max=salary_max,
        notes=notes,
    )
    response = Response(status_code=204)
    response.headers["HX-Redirect"] = "/tracking"
    return response


@router.put("/api/v1/applications/{application_id}/status", name="applications_put_status")
async def put_application_status(
    application_id: int,
    payload: Annotated[dict[str, Any], Body()],
):
    status_str = payload.get("status")
    if not status_str:
        raise HTTPException(status_code=422, detail="`status` required")
    try:
        new_status = ApplicationStatus(status_str)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unknown status {status_str!r}") from None
    closed_reason = None
    if new_status == ApplicationStatus.CLOSED:
        cr = payload.get("closed_reason")
        if not cr:
            raise HTTPException(
                status_code=422, detail="`closed_reason` required when status=CLOSED"
            )
        closed_reason = ClosedReason(cr)
    a = await sd._apply_status_override(application_id, new_status, closed_reason=closed_reason)
    if a is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return a.model_dump(mode="json")


@router.delete("/api/v1/applications/{application_id}/discard", name="applications_discard")
async def delete_application_discard(application_id: int):
    a = await sd._apply_status_override(
        application_id,
        ApplicationStatus.CLOSED,
        closed_reason=ClosedReason.WITHDRAWN_BY_ME,
    )
    if a is None:
        raise HTTPException(status_code=404, detail="Application not found")
    a.deleted_at = datetime.now(UTC)
    response = Response(status_code=204)
    response.headers["HX-Redirect"] = "/discover"
    return response


@router.post("/api/v1/applications/{application_id}/submit", name="applications_submit")
async def post_application_submit(application_id: int):
    """Validate + flip DRAFT → APPLIED.

    409 if any required screener answers are unreviewed.
    """
    a = await sd.get_application(application_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Application not found")
    if a.status != ApplicationStatus.DRAFT:
        raise HTTPException(status_code=409, detail="Application not in DRAFT")
    unreviewed = await sd.unreviewed_required_screeners(application_id)
    if unreviewed > 0:
        raise HTTPException(
            status_code=409,
            detail=f"{unreviewed} required screener answers unreviewed",
        )
    a.status = ApplicationStatus.APPLIED
    a.applied_at = datetime.now(UTC)
    a.updated_at = datetime.now(UTC)
    if a.job_id is not None:
        await sd._set_job_queue_state(
            a.job_id,
            __import__("models.enums", fromlist=["JobQueueState"]).JobQueueState.APPLIED,
        )
    response = Response(status_code=204)
    response.headers["HX-Redirect"] = "/tracking"
    return response


@router.get("/api/v1/applications", name="applications_list")
async def get_applications(
    status: Annotated[str | None, Query()] = None,
    closed: Annotated[int, Query()] = 0,
):
    if status:
        try:
            apps = await sd.applications_by_status(ApplicationStatus(status))
        except ValueError:
            raise HTTPException(status_code=422, detail="Unknown status") from None
    elif closed:
        apps = await sd.closed_applications()
    else:
        apps = await sd.applications_visible_in_tracking()
    return {"items": [a.model_dump(mode="json") for a in apps], "next_cursor": None}


@router.get("/api/v1/applications/{application_id}", name="applications_get")
async def get_application(application_id: int):
    a = await sd.get_application(application_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return a.model_dump(mode="json")


@router.get("/api/v1/applications/{application_id}/bundle", name="applications_bundle")
async def get_application_bundle(application_id: int):
    """Stub bundle — returns a tiny ZIP placeholder so the link works end-to-end."""
    import io
    import zipfile

    a = await sd.get_application(application_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Application not found")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("metadata.json", f'{{"application_id": {application_id}}}')
        zf.writestr("resume.pdf", "%PDF-1.4\n%placeholder\n")
        zf.writestr("cover-letter.pdf", "%PDF-1.4\n%placeholder\n")
        zf.writestr("screener-answers.json", "[]")
    buf.seek(0)
    return Response(
        content=buf.read(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="bundle-{application_id}.zip"'},
    )
