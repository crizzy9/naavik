"""Auth-shell routes (Login, Onboarding) — placeholder bodies for plan 08.

Plan 09 swaps the placeholder for real page templates. Plan 10 wires the JWT
cookie + bcrypt auth dependency.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ui.templates_setup import templates

router = APIRouter()


@router.get("/login", response_class=HTMLResponse, name="login")
async def get_login(request: Request):
    return templates.TemplateResponse(
        request,
        "placeholder.html",
        {
            "screen": "Login",
            "route": "/login",
            "section": "1",
            "active_sidebar": None,  # auth shell — no sidebar.
            "active_template_path": "/login",
        },
    )


@router.get("/onboarding", response_class=HTMLResponse, name="onboarding")
async def get_onboarding(request: Request):
    return templates.TemplateResponse(
        request,
        "placeholder.html",
        {
            "screen": "Onboarding · resume upload",
            "route": "/onboarding",
            "section": "2",
            # Onboarding is auth-shell too, but per the prompt we set
            # active_sidebar="overview" so any sidebar peek lands somewhere
            # reasonable — the placeholder.html is rendered with sidebar today,
            # plan 09 will swap to the auth_shell extender + drop the sidebar.
            "active_sidebar": "overview",
            "active_template_path": "/onboarding",
        },
    )
