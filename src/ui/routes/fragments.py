"""HTMX fragment routes — modals + cross-cutting partials.

Plan 08 shipped `/_modal/confirm`. Plan 09 adds:
- GET /_modal/bullet-editor/{bullet_id}      — bullet editor modal (Section 6)
- GET /_fragments/onboarding/step/{n}        — onboarding step partial (Section 2)
- GET /_fragments/profile/bullet-row/{id}    — single bullet row reload
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from db import sample_data as sd
from ui import profile_ctx as pctx
from ui.templates_setup import templates

router = APIRouter()


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
async def bullet_editor_modal(request: Request, bullet_id: int):
    bullet = await sd.get_bullet(bullet_id)
    if bullet is None:
        raise HTTPException(status_code=404, detail="Bullet not found")
    exp = await sd.get_experience(bullet.experience_id)
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
async def profile_bullet_row(request: Request, bullet_id: int):
    bullet = await sd.get_bullet(bullet_id)
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
    if step not in (1, 2, 3):
        raise HTTPException(status_code=404, detail="Unknown step")
    template_map = {
        1: "pages/_onboarding_step_upload.html",
        2: "pages/_onboarding_step_extracting.html",
        3: "pages/_onboarding_step_review.html",
    }
    return templates.TemplateResponse(
        request,
        template_map[step],
        {"extraction_id": "fake-1"},
    )
