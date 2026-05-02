"""Discover + Discover · review routes — placeholder bodies for plan 08."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ui.templates_setup import templates

router = APIRouter()


@router.get("/discover", response_class=HTMLResponse, name="discover")
async def get_discover(request: Request):
    return templates.TemplateResponse(
        request,
        "placeholder.html",
        {
            "screen": "Discover",
            "route": "/discover",
            "section": "7",
            "active_sidebar": "jobs",
            "active_template_path": "/discover",
        },
    )


@router.get("/discover/{job_id}", response_class=HTMLResponse, name="discover_review")
async def get_review(request: Request, job_id: str):
    return templates.TemplateResponse(
        request,
        "placeholder.html",
        {
            "screen": "Discover · review & apply",
            "route": f"/discover/{job_id}",
            "section": "8",
            "active_sidebar": "jobs",
            "active_template_path": "/discover/:id",
        },
    )
