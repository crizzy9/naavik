"""Settings routes — placeholder bodies for plan 08.

`/settings` and `/settings/{tab}` both render the placeholder. Plan 09 swaps in
the real Settings page composition.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ui.templates_setup import templates

router = APIRouter()


@router.get("/settings", response_class=HTMLResponse, name="settings")
async def get_settings(request: Request):
    return templates.TemplateResponse(
        request,
        "placeholder.html",
        {
            "screen": "Settings",
            "route": "/settings",
            "section": "11",
            "active_sidebar": "settings",
            "active_template_path": "/settings",
        },
    )


@router.get("/settings/{tab}", response_class=HTMLResponse, name="settings_tab")
async def get_settings_tab(request: Request, tab: str):
    return templates.TemplateResponse(
        request,
        "placeholder.html",
        {
            "screen": f"Settings · {tab}",
            "route": f"/settings/{tab}",
            "section": "11",
            "active_sidebar": "settings",
            "active_template_path": "/settings/:tab",
        },
    )
