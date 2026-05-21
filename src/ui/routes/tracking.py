"""Tracking route + fragment + JSON stubs."""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from api.auth import require_csrf
from config import settings as app_settings
from db.session import get_session
from models import User
from models.enums import ApplicationStatus, ClosedReason
from services import application_service
from services.auth import require_authed_session
from ui import tracking_ctx as tctx
from ui.templates_setup import templates

# Mirrors `api.applications._POSTMORTEM_TS_RE` (plan 52). Strict UTC-stamp
# regex blocks path-traversal payloads at the routing layer.
_POSTMORTEM_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z$")

router = APIRouter()


def _effective_user_id(user: User | None) -> int:
    return user.id if user is not None else 1


# ─────────────────────────────────────────────────────────────────────────
# Page handler
# ─────────────────────────────────────────────────────────────────────────


@router.get("/tracking", response_class=HTMLResponse, name="tracking")
async def get_tracking(
    request: Request,
    view: Annotated[Literal["board", "list"], Query()] = "board",
    show_closed: Annotated[int, Query()] = 0,
    show_drafts: Annotated[int, Query()] = 0,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    ctx = await tctx.build_tracking_ctx(
        session,
        user_id=_effective_user_id(user),
        view=view,
        show_closed=bool(show_closed),
        show_drafts=bool(show_drafts),
    )
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
    show_drafts: Annotated[int, Query()] = 0,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    ctx = await tctx.build_tracking_ctx(
        session,
        user_id=_effective_user_id(user),
        view="board",
        show_closed=bool(show_closed),
        show_drafts=bool(show_drafts),
    )
    return templates.TemplateResponse(request, "pages/_tracking_board.html", ctx)


@router.get("/_fragments/tracking/list", response_class=HTMLResponse, name="tracking_list_fragment")
async def fragment_list(
    request: Request,
    show_drafts: Annotated[int, Query()] = 0,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    ctx = await tctx.build_tracking_ctx(
        session,
        user_id=_effective_user_id(user),
        view="list",
        show_closed=True,
        show_drafts=bool(show_drafts),
    )
    return templates.TemplateResponse(request, "pages/_tracking_list.html", ctx)


@router.get(
    "/_fragments/tracking/followup-banner",
    response_class=HTMLResponse,
    name="tracking_followup_fragment",
)
async def fragment_followup(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    ctx = await tctx.build_tracking_ctx(session, user_id=_effective_user_id(user), view="board")
    if ctx["followup_count"] == 0:
        return HTMLResponse("")
    return templates.TemplateResponse(
        request,
        "components/followup_banner.html",
        {"count": ctx["followup_count"], "items": ctx["followup_items"]},
    )


# ─────────────────────────────────────────────────────────────────────────
# Application detail slide-over (plan 53 § C / 0.2.4.03)
# ─────────────────────────────────────────────────────────────────────────


async def _application_or_404(session: AsyncSession, application_id: int, user: User | None):
    """Fetch an Application and enforce user_id boundary (IDOR → 404, never 403)."""
    a = await application_service.get_application(session, application_id)
    if a is None or a.user_id != _effective_user_id(user):
        raise HTTPException(status_code=404, detail="Application not found")
    return a


@router.get("/tracking/{application_id}", response_class=HTMLResponse, name="tracking_detail")
async def get_tracking_detail(
    request: Request,
    application_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    application = await _application_or_404(session, application_id, user)
    base_ctx = await tctx.build_tracking_ctx(
        session, user_id=_effective_user_id(user), view="board"
    )
    detail_ctx = await tctx.build_application_detail_ctx(session, application)
    ctx = {**base_ctx, **detail_ctx}
    ctx["active_sidebar"] = "tracking"
    ctx["active_template_path"] = "/tracking"
    ctx["slide_over_open"] = True
    return templates.TemplateResponse(request, "pages/tracking.html", ctx)


@router.get(
    "/_fragments/tracking/application/{application_id}",
    response_class=HTMLResponse,
    name="tracking_application_fragment",
)
async def fragment_application(
    request: Request,
    application_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    application = await _application_or_404(session, application_id, user)
    ctx = await tctx.build_application_detail_ctx(session, application)
    return templates.TemplateResponse(request, "components/_application_detail.html", ctx)


# ─────────────────────────────────────────────────────────────────────────
# Plan 81 § D.1 (0.4.0.10) — postmortem modal overlay
# ─────────────────────────────────────────────────────────────────────────


@router.get(
    "/_modal/postmortem/{application_id}/{ts}",
    response_class=HTMLResponse,
    name="tracking_postmortem_modal",
)
async def get_postmortem_modal(
    request: Request,
    application_id: int,
    ts: str,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    """Render the postmortem-modal partial for `application_id` + `ts`.

    Path-traversal gauntlet matches `api.applications.get_postmortem` (plan 52):
    1. Strict UTC-timestamp regex on `ts` (`_POSTMORTEM_TS_RE`).
    2. `Path.resolve().relative_to(data_root)` containment check.
    3. IDOR via `_application_or_404` (404 on cross-user / missing).
    """
    # IDOR + existence check first — never leak postmortem existence to
    # non-owners by varying the 404/400 code based on app presence.
    await _application_or_404(session, application_id, user)
    if not _POSTMORTEM_TS_RE.match(ts):
        raise HTTPException(status_code=404, detail="postmortem not found")
    data_root = Path(app_settings.data_dir).expanduser().resolve() / "data" / "postmortems"
    base = (data_root / str(application_id) / ts).resolve()
    try:
        base.relative_to(data_root)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="postmortem not found") from exc

    trace_file = base / "trace.json"
    analysis_file = base / "analysis.md"
    if not trace_file.exists() or not analysis_file.exists():
        raise HTTPException(status_code=404, detail="postmortem not found")

    try:
        trace = json.loads(trace_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        trace = {}
    analysis_md = analysis_file.read_text(encoding="utf-8")

    return templates.TemplateResponse(
        request,
        "components/postmortem_modal.html",
        {
            "application_id": application_id,
            "ts": ts,
            "trace": trace,
            "analysis_md": analysis_md,
        },
    )


# ─────────────────────────────────────────────────────────────────────────
# JSON stubs for application moves + manual entry + status overrides
# ─────────────────────────────────────────────────────────────────────────


@router.post(
    "/api/v1/applications/{application_id}/retry",
    name="applications_retry",
)
async def post_retry_application(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    """Plan 79 / 0.4.0.11 — clear `last_failure` + re-queue stuck DRAFT."""
    try:
        await application_service.retry_failed(
            session, application_id, user_id=_effective_user_id(user)
        )
    except application_service.IllegalStateTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except application_service.ApplicationServiceError:
        raise HTTPException(status_code=404, detail="Application not found") from None
    await session.commit()
    return Response(status_code=204, headers={"HX-Trigger": "applicationRetried"})


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
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    """Create a manually-entered Application (plan 56 / 0.2.7.19 — CSRF-gated)."""
    await application_service.create_manual(
        session,
        user_id=_effective_user_id(user),
        company=company,
        role=role,
        team=team,
        location=location,
        salary_min=salary_min,
        salary_max=salary_max,
        notes=notes,
    )
    await session.commit()
    response = Response(status_code=204)
    response.headers["HX-Redirect"] = "/tracking"
    return response


@router.get("/api/v1/applications", name="applications_list")
async def get_applications(
    status: Annotated[str | None, Query()] = None,
    closed: Annotated[int, Query()] = 0,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    user_id = _effective_user_id(user)
    if status:
        try:
            status_enum = ApplicationStatus(status)
        except ValueError:
            raise HTTPException(status_code=422, detail="Unknown status") from None
        apps = await application_service.list_by_status(session, user_id, status_enum)
    elif closed:
        apps = await application_service.list_closed(session, user_id)
    else:
        apps = await application_service.list_visible_in_tracking(session, user_id)
    return {"items": [a.model_dump(mode="json") for a in apps], "next_cursor": None}


_EXPORT_FIELDNAMES = [
    "company",
    "role",
    "team",
    "location",
    "status",
    "applied_at",
    "salary_min",
    "salary_max",
    "board",
    "external_url",
]


# Registered BEFORE the parameterized `/applications/{application_id}` so
# the literal `export.csv` path doesn't get parsed as an int application_id.
@router.get("/api/v1/applications/export.csv", name="applications_export_csv")
async def get_applications_export_csv(
    application_ids: Annotated[list[int] | None, Query()] = None,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    """Export selected applications as CSV. Auth-gated; cap 50 IDs."""
    user_id = _effective_user_id(user)
    ids = application_ids or []
    try:
        rows = await application_service.list_for_export(
            session,
            user_id=user_id,
            application_ids=ids,
        )
    except application_service.ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_EXPORT_FIELDNAMES)
    writer.writeheader()
    writer.writerows(rows)
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="applications.csv"',
        },
    )


@router.get("/api/v1/applications/{application_id}", name="applications_get")
async def get_application(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    a = await application_service.get_application(session, application_id)
    if a is None or a.user_id != _effective_user_id(user):
        raise HTTPException(status_code=404, detail="Application not found")
    return a.model_dump(mode="json")


@router.get("/api/v1/applications/{application_id}/bundle", name="applications_bundle")
async def get_application_bundle(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    """Stub bundle — returns a tiny ZIP placeholder so the link works end-to-end."""
    import io
    import zipfile

    a = await application_service.get_application(session, application_id)
    if a is None or a.user_id != _effective_user_id(user):
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


# ─────────────────────────────────────────────────────────────────────────
# Bulk actions on /tracking list view (plan 80 / 0.4.0.09)
# ─────────────────────────────────────────────────────────────────────────


def _bulk_toast_header(success: int, failed: int) -> str:
    return json.dumps({"showToast": {"text": f"Updated {success}, skipped {failed}"}})


@router.post(
    "/_fragments/tracking/bulk/move-stage",
    response_class=HTMLResponse,
    name="tracking_bulk_move_stage",
)
async def post_bulk_move_stage(
    request: Request,
    application_ids: Annotated[list[int], Form()],
    new_status: Annotated[str, Form()],
    closed_reason: Annotated[str | None, Form()] = None,
    show_drafts: Annotated[int, Form()] = 0,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    """Bulk-move selected applications to ``new_status``.

    Returns the updated tracking list fragment + an ``HX-Trigger`` toast
    summary. 422 on unknown enum or > 50 IDs.
    """
    try:
        status_enum = ApplicationStatus(new_status)
    except ValueError:
        raise HTTPException(status_code=422, detail="Unknown status") from None
    cr_enum: ClosedReason | None
    if closed_reason:
        try:
            cr_enum = ClosedReason(closed_reason)
        except ValueError:
            raise HTTPException(status_code=422, detail="Unknown closed_reason") from None
    else:
        cr_enum = None

    user_id = _effective_user_id(user)
    try:
        success, failed = await application_service.bulk_update_status(
            session,
            user_id=user_id,
            application_ids=application_ids,
            new_status=status_enum,
            closed_reason=cr_enum,
        )
    except application_service.ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    await session.commit()

    ctx = await tctx.build_tracking_ctx(
        session,
        user_id=user_id,
        view="list",
        show_closed=True,
        show_drafts=bool(show_drafts),
    )
    response = templates.TemplateResponse(request, "pages/_tracking_list.html", ctx)
    response.headers["HX-Trigger"] = _bulk_toast_header(success, len(failed))
    return response


@router.post(
    "/_fragments/tracking/bulk/archive",
    response_class=HTMLResponse,
    name="tracking_bulk_archive",
)
async def post_bulk_archive(
    request: Request,
    application_ids: Annotated[list[int], Form()],
    show_drafts: Annotated[int, Form()] = 0,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    """Bulk archive — closes selected applications w/ USER_ARCHIVED reason."""
    user_id = _effective_user_id(user)
    try:
        success, failed = await application_service.bulk_archive(
            session,
            user_id=user_id,
            application_ids=application_ids,
        )
    except application_service.ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    await session.commit()

    ctx = await tctx.build_tracking_ctx(
        session,
        user_id=user_id,
        view="list",
        show_closed=True,
        show_drafts=bool(show_drafts),
    )
    response = templates.TemplateResponse(request, "pages/_tracking_list.html", ctx)
    response.headers["HX-Trigger"] = _bulk_toast_header(success, len(failed))
    return response
