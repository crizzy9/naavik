"""Tracking route — placeholder body for plan 08."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ui.templates_setup import templates

router = APIRouter()


@router.get("/tracking", response_class=HTMLResponse, name="tracking")
async def get_tracking(request: Request):
    return templates.TemplateResponse(
        request,
        "placeholder.html",
        {
            "screen": "Tracking",
            "route": "/tracking",
            "section": "9",
            "active_sidebar": "tracking",
            "active_template_path": "/tracking",
        },
    )
