"""Design fixture route — `/_design/components`.

Renders every component in every variant. Useful for visual QA during plan 08.

Phase 1 gate: env var NAAVIK_DEBUG=1.
Plan 10 Wave 3 swaps to the persisted `Settings.debug` flag.
"""

import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from ui.templates_setup import templates

router = APIRouter()


def _debug_enabled() -> bool:
    return os.environ.get("NAAVIK_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}


@router.get("/_design/components", response_class=HTMLResponse, name="design_components")
async def design_components(request: Request):
    if not _debug_enabled():
        raise HTTPException(status_code=404, detail="Not Found")
    return templates.TemplateResponse(
        request,
        "pages/_design_components.html",
        {
            "active_sidebar": None,  # not in main IA
            "active_template_path": "/_design/components",
        },
    )
