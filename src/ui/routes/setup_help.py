"""`/setup-help` — public first-run diagnostic page (plan 83 / 0.7.0.36).

After plan 83 deleted the auto-seed dev user + `~/.naavik/dev-credentials`
artifact, this page collapses to a thin redirect surface:

- DB has no users → "Visit /signup to create your account"
- DB has at least one user → "Visit /login to sign in"

No auth required — operators reach this when their login flow stalled
or when they're following the RUNBOOK link.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from db.session import get_session
from services.utils import first_run
from ui.templates_setup import templates

router = APIRouter()


# Anchor into docs/RUNBOOK.md § 2.12 First-run authentication.
_RUNBOOK_ANCHOR = "#212-first-run-authentication--401-troubleshooting"


@router.get("/setup-help", response_class=HTMLResponse, name="setup_help")
async def get_setup_help(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Render the diagnostic + recovery page (unauthenticated)."""
    state = await first_run.probe_first_run_state(session)
    return templates.TemplateResponse(
        request,
        "pages/auth/setup_help.html",
        {
            "active_sidebar": None,
            "active_template_path": "/setup-help",
            "state": state,
            "runbook_anchor": _RUNBOOK_ANCHOR,
        },
    )
