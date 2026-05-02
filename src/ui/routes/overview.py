"""Overview route — placeholder body for plan 08."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ui.templates_setup import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse, name="overview")
async def get_overview(request: Request):
    return templates.TemplateResponse(
        request,
        "placeholder.html",
        {
            "screen": "Overview",
            "route": "/",
            "section": "3",
            "active_sidebar": "overview",
            "active_template_path": "/",
        },
    )
