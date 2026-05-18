"""Real `/api/v1/profile/*` and `/api/v1/bullets/*` handlers.

Wave 4 of plan 10 § B.7. Replaces the plan-09 stubs in
`src/ui/routes/profile.py` for state-changing endpoints. Page handlers
(`GET /profile`, `GET /profile/edit`) stay in `src/ui/routes/profile.py`.

These mount under `/api/v1/profile` + `/api/v1/bullets`.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Form, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from db.session import get_session
from models import User
from services import profile_service
from services.auth import require_authed_session
from ui.templates_setup import templates

router = APIRouter()


# ── Per-field PUT (autosave) ────────────────────────────────────────────


@router.put("/api/v1/profile/{field}", name="api_profile_put_field")
async def put_field(
    request: Request,
    field: str,
    fail: Annotated[str | None, Query()] = None,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
):
    """Per-field autosave. Returns the OOB autosave indicator partial."""
    if fail:
        return templates.TemplateResponse(
            request,
            "components/autosave_indicator.html",
            {"state": "error", "error_message": "Couldn't save — retry"},
            status_code=422,
        )
    if field not in profile_service.ALLOWED_PROFILE_FIELDS:
        raise HTTPException(status_code=404, detail="Unknown field")

    # Read raw form value — accept any string; service-layer coerces.
    form = await request.form()
    raw_value = form.get("value")

    try:
        # Single-user MVP: user_id=1.
        await profile_service.update_field(
            session,
            user_id=1,
            field=field,
            value=raw_value,
        )
        await session.commit()
    except (LookupError, ValueError) as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return templates.TemplateResponse(
        request,
        "components/autosave_indicator.html",
        {"state": "saved", "relative_time": "just now"},
    )


@router.put("/api/v1/profile/application-questions", name="api_profile_put_application_questions")
async def put_application_questions(
    request: Request,
    payload: Annotated[dict[str, Any] | None, Body()] = None,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
):
    payload = payload or {}
    try:
        await profile_service.update_application_questions(
            session,
            user_id=1,
            payload=payload,
        )
        await session.commit()
    except LookupError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


# ── Bullets ─────────────────────────────────────────────────────────────


@router.post("/api/v1/bullets", name="api_bullets_post")
async def post_bullet(
    request: Request,
    text: Annotated[str, Form()] = "",
    experience_id: Annotated[int, Form()] = 0,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
):
    if not experience_id:
        raise HTTPException(status_code=422, detail="experience_id is required")
    bullet = await profile_service.add_bullet(
        session,
        experience_id=experience_id,
        text=text,
        tags=["backend"],
    )
    await session.commit()
    return _bullet_row_response(request, bullet)


@router.put("/api/v1/bullets/{bullet_id}", name="api_bullets_put")
async def put_bullet(
    request: Request,
    bullet_id: int,
    text: Annotated[str | None, Form()] = None,
    fail: Annotated[str | None, Query()] = None,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
):
    if fail:
        raise HTTPException(status_code=422, detail="Couldn't save bullet")
    try:
        bullet = await profile_service.update_bullet(session, bullet_id, text=text)
        await session.commit()
    except LookupError as exc:
        await session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    response = _bullet_row_response(request, bullet)
    response.headers["HX-Trigger"] = "closeModal"
    return response


@router.delete("/api/v1/bullets/{bullet_id}", name="api_bullets_delete")
async def delete_bullet(
    bullet_id: int,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
):
    deleted = await profile_service.delete_bullet(session, bullet_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Bullet not found")
    await session.commit()
    response = Response(status_code=204)
    response.headers["HX-Trigger"] = "closeModal, bulletDeleted"
    return response


@router.post("/api/v1/bullets/{bullet_id}/rewrite", name="api_bullets_rewrite")
async def post_bullet_rewrite(
    bullet_id: int,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
):
    """Stub LLM rewrite — Wave 6 wires `prompts/auto_tag_bullets` + a rewrite prompt."""
    bullet = await profile_service.get_bullet(session, bullet_id)
    if bullet is None:
        raise HTTPException(status_code=404, detail="Bullet not found")
    return {
        "id": bullet.id,
        "text": bullet.text + " (rewritten by AI)",
        "tags": list(bullet.tags or []),
        "edited": True,
    }


@router.post("/api/v1/bullets/reorder", name="api_bullets_reorder")
async def post_bullets_reorder(
    payload: Annotated[dict[str, Any] | None, Body()] = None,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
):
    payload = payload or {}
    bullet_ids = payload.get("bullet_ids") or []
    experience_id = payload.get("experience_id")
    # Best-effort across-experience reorder if `experience_id` is omitted —
    # plan-09 was loose about this.
    if not experience_id:
        # Need experience_id to scope; fall back to no-op.
        return Response(status_code=204)
    try:
        ids = [int(bid) for bid in bullet_ids]
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="bullet_ids must be ints") from exc
    await profile_service.reorder_bullets(
        session,
        experience_id=int(experience_id),
        bullet_ids=ids,
    )
    await session.commit()
    return Response(status_code=204)


# ── Helpers ──────────────────────────────────────────────────────────────


def _bullet_row_response(request: Request, bullet) -> HTMLResponse:
    """Render the bullet_edit_row partial — same shape plan 09 produced."""
    return templates.TemplateResponse(
        request,
        "components/bullet_edit_row.html",
        {
            "bullet": {
                "id": bullet.id,
                "experience_id": bullet.experience_id,
                "text": bullet.text,
                "tags": list(bullet.tags or []),
                "selection_override": (
                    bullet.selection_override.value if bullet.selection_override else None
                ),
                "edited": True,
                "edited_at_display": "just now",
            },
        },
    )
