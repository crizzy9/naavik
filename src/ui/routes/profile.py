"""Profile + Profile-editor routes — placeholder bodies for plan 08."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ui.templates_setup import templates

router = APIRouter()


@router.get("/profile", response_class=HTMLResponse, name="profile")
async def get_profile(request: Request):
    return templates.TemplateResponse(
        request,
        "placeholder.html",
        {
            "screen": "Profile",
            "route": "/profile",
            "section": "4",
            "active_sidebar": "profile",
            "active_template_path": "/profile",
        },
    )


@router.get("/profile/edit", response_class=HTMLResponse, name="profile_edit")
async def get_edit(request: Request):
    return templates.TemplateResponse(
        request,
        "placeholder.html",
        {
            "screen": "Profile editor",
            "route": "/profile/edit",
            "section": "5",
            "active_sidebar": "profile",
            "active_template_path": "/profile/edit",
        },
    )
