"""Tracking route + fragment + JSON stubs."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from api.auth import require_csrf
from db.session import get_session
from models import User
from models.enums import ApplicationStatus
from services import application_service
from services.auth import require_authed_session
from ui import tracking_ctx as tctx
from ui.templates_setup import templates

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
# JSON stubs for application moves + manual entry + status overrides
# ─────────────────────────────────────────────────────────────────────────


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
