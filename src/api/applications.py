"""Real `/api/v1/applications/*` handlers — Wave 6.

Per BACKEND.md § D.4 + plan 10 § C.3. Replaces the stubs that lived under
`ui/routes/tracking.py` (move/discard/submit) with service-layer-backed
handlers that go through `application_service.submit_draft / discard_draft /
update_status`.

Page handlers (`GET /tracking`, etc.) stay in `ui/routes/`; only the JSON
mutation endpoints move here.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Response
from sqlmodel.ext.asyncio.session import AsyncSession

from db.session import get_session
from models import ApplicationStatus, ClosedReason, User
from services import application_service as svc
from services.auth import get_current_user

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/applications")


@router.post("/{application_id}/submit", name="api_applications_submit")
async def submit(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """DRAFT → APPLIED. Validates first; returns the row or 409 with the reason."""
    try:
        out = await svc.submit_draft(session, application_id)
    except svc.ValidationError as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": str(exc)}) from exc
    except svc.ApplicationServiceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    # Caller (HTMX) wants HX-Redirect on success.
    if out.status == ApplicationStatus.APPLIED:
        await session.commit()
        response = Response(status_code=204)
        response.headers["HX-Redirect"] = "/tracking"
        return response

    # Persistent failure — caller renders banner from submission_artifacts.
    last_failure = (out.submission_artifacts or {}).get("last_failure", {})
    return {
        "id": out.id,
        "status": out.status.value,
        "last_failure": last_failure,
    }


@router.delete("/{application_id}/discard", name="api_applications_discard")
async def discard(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    try:
        await svc.discard_draft(session, application_id)
    except svc.IllegalStateTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except svc.ApplicationServiceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    response = Response(status_code=204)
    response.headers["HX-Redirect"] = "/discover"
    return response


@router.put("/{application_id}/status", name="api_applications_put_status")
async def put_status(
    application_id: int,
    payload: Annotated[dict[str, Any], Body()],
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    raw = payload.get("status")
    if not raw:
        raise HTTPException(status_code=422, detail="`status` required")
    try:
        new_status = ApplicationStatus(raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Unknown status {raw!r}") from exc
    cr = payload.get("closed_reason")
    closed_reason = None
    if new_status == ApplicationStatus.CLOSED:
        if not cr:
            raise HTTPException(
                status_code=422,
                detail="`closed_reason` required when status=CLOSED",
            )
        try:
            closed_reason = ClosedReason(cr)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"Unknown closed_reason {cr!r}") from exc
    try:
        out = await svc.update_status(
            session,
            application_id,
            new_status,
            closed_reason=closed_reason,
            notes=payload.get("notes"),
        )
    except svc.ValidationError as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": str(exc)}) from exc
    except svc.ApplicationServiceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    return out.model_dump(mode="json")


@router.post("/move", name="api_applications_move")
async def move(
    payload: Annotated[dict[str, Any] | None, Body()] = None,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    if not payload:
        return Response(status_code=204)
    app_id = int(payload.get("application_id", 0))
    target = payload.get("target_status")
    if not (app_id and target):
        return Response(status_code=204)
    try:
        new_status = ApplicationStatus(target)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Bad status") from exc
    closed_reason = None
    if new_status == ApplicationStatus.CLOSED:
        cr = payload.get("closed_reason")
        if cr:
            closed_reason = ClosedReason(cr)
    try:
        await svc.update_status(
            session, app_id, new_status, closed_reason=closed_reason
        )
    except svc.ApplicationServiceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    return Response(status_code=204)


@router.get("/stuck", name="api_applications_stuck")
async def get_stuck(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Stuck-queue endpoint — DRAFTs with `submission_artifacts.last_failure`.

    Vault boundary: scoped to the current user. Powers the Discover right
    rail "Stuck in queue" card.
    """
    apps = await svc.stuck_drafts(session, user_id=current_user.id)
    return {
        "items": [
            {
                "id": a.id,
                "company": a.company,
                "role": a.role,
                "board": a.board.value if a.board else None,
                "last_failure": (a.submission_artifacts or {}).get("last_failure"),
            }
            for a in apps
        ]
    }
