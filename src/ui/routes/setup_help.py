"""`/setup-help` — public first-run diagnostic page (plan 71 / 0.3.3.14).

When the operator hits the plan-10c trifecta — `NAAVIK_DEBUG` unset AND
users seeded AND no `~/.naavik/dev-credentials` artifact — they're
locked out of both `/login` (no creds) and `/login?mode=signup` (gate
disabled). This page surfaces the diagnosis + copy-pasteable recovery
recipes. No auth required: this IS the auth-help surface.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from db.session import get_session
from services import first_run
from ui.templates_setup import templates

router = APIRouter()


# Anchor into docs/RUNBOOK.md § 2.12 First-run authentication. Kept as a
# constant so tests can assert the link is wired without parsing markdown.
_RUNBOOK_ANCHOR = "#212-first-run-authentication--401-troubleshooting"


@router.get("/setup-help", response_class=HTMLResponse, name="setup_help")
async def get_setup_help(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Render the diagnostic + recovery page.

    Unauthenticated by design — operators reach this exactly when their
    auth flow is broken. Probes via `services.first_run.probe_first_run_state`,
    which the lifespan WARN logger also consumes (single canonical
    diagnostic shape).
    """
    state = await first_run.probe_first_run_state(session)
    return templates.TemplateResponse(
        request,
        "pages/setup_help.html",
        {
            "active_sidebar": None,
            "active_template_path": "/setup-help",
            "state": state,
            "runbook_anchor": _RUNBOOK_ANCHOR,
        },
    )
