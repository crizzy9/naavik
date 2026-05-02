"""HTMX fragment routes (modals, OOB swaps, etc.).

Phase 1 plan 08 ships:
- GET /_modal/confirm?title=&message=&action=&label=&tone=&method=
  Centralized confirmation modal per INTERACTIONS.md § E.4.
"""

from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ui.templates_setup import templates

router = APIRouter()


@router.get("/_modal/confirm", response_class=HTMLResponse, name="modal_confirm")
async def confirm_modal(
    request: Request,
    title: str,
    message: str,
    action: str,
    label: str = "Confirm",
    tone: Literal["danger", "warning", "primary"] = "danger",
    method: Literal["post", "delete", "put", "patch"] = "post",
    cancel_label: str = "Cancel",
):
    """Render confirm_modal.html from query params.

    Trigger pattern (per INTERACTIONS.md § E.4):
        <button hx-get="/_modal/confirm?title=Delete+bullet&message=...&action=/api/v1/bullets/42&label=Delete&tone=danger&method=delete"
                hx-target="#modal-region" hx-swap="innerHTML">Delete</button>
    """
    return templates.TemplateResponse(
        request,
        "components/confirm_modal.html",
        {
            "title": title,
            "message": message,
            "confirm_action_url": action,
            "confirm_label": label,
            "confirm_tone": tone,
            "confirm_method": method,
            "cancel_label": cancel_label,
        },
    )
