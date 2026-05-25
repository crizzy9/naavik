"""Design fixture route — `/_design/components`.

Renders every component in every variant. Useful for visual QA during plan 08.

Wave 4 swap: gate is now persisted `Settings.debug` (not `NAAVIK_DEBUG` env).
For tests that don't have a live DB, the legacy env var still works as a
fallback so plan-09 component tests keep passing.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from db.session import get_session
from services.settings_service import get_or_create
from ui.templates_setup import templates

router = APIRouter()


def _legacy_env_gate() -> bool:
    return os.environ.get("NAAVIK_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}


async def _settings_gate(session: AsyncSession) -> bool:
    """True iff any user has `Settings.debug=True`. Single-user MVP — first row wins."""
    try:
        # Cheap: read settings for user_id=1 (dev/seed convention; multi-user
        # wiring is post-0.7.0.48 follow-up).
        s = await get_or_create(session, user_id=1)
        return bool(s.debug)
    except Exception:
        # Migration not yet applied / DB unreachable — fall through to env gate.
        return False


@router.get("/_design/components", response_class=HTMLResponse, name="design_components")
async def design_components(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    if not _legacy_env_gate():
        # Wave 4 default path: consult the DB-backed Settings.debug.
        try:
            db_gate = await _settings_gate(session)
        except Exception:
            db_gate = False
        if not db_gate:
            raise HTTPException(status_code=404, detail="Not Found")
    return templates.TemplateResponse(
        request,
        "pages/_design_components.html",
        {
            "active_sidebar": None,
            "active_template_path": "/_design/components",
        },
    )
