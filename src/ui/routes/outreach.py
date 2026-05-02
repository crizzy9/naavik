"""Outreach route — placeholder body for plan 08."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ui.templates_setup import templates

router = APIRouter()


@router.get("/outreach", response_class=HTMLResponse, name="outreach")
async def get_outreach(request: Request):
    return templates.TemplateResponse(
        request,
        "placeholder.html",
        {
            "screen": "Outreach",
            "route": "/outreach",
            "section": "10",
            "active_sidebar": "outreach",
            "active_template_path": "/outreach",
        },
    )
