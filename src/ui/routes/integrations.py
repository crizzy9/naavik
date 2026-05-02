"""Integration OAuth stubs (Gmail / Outlook / Calendar) per BACKEND.md § D.5."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response
from fastapi.responses import RedirectResponse

router = APIRouter()

# In-memory integration state — server-process scoped, resets on restart.
_INTEGRATIONS: dict[str, dict[str, object]] = {
    "gmail": {
        "provider": "gmail",
        "account": "[email protected]",
        "last_sync_at": datetime.now(UTC).isoformat(),
        "status": "connected",
    },
    "outlook": {
        "provider": "outlook",
        "account": None,
        "last_sync_at": None,
        "status": "not_connected",
    },
    "calendar": {
        "provider": "calendar",
        "account": None,
        "last_sync_at": None,
        "status": "not_connected",
    },
}


@router.get("/api/v1/integrations", name="integrations_list")
async def list_integrations():
    return list(_INTEGRATIONS.values())


def _provider_routes(provider: str) -> tuple[str, str]:
    return (
        f"/api/v1/integrations/{provider}/callback?code=fake-1",
        f"/tracking?connected={provider}",
    )


@router.get("/api/v1/integrations/gmail/connect", name="gmail_connect")
async def gmail_connect():
    callback, _ = _provider_routes("gmail")
    return RedirectResponse(url=callback, status_code=302)


@router.get("/api/v1/integrations/gmail/callback", name="gmail_callback")
async def gmail_callback(code: Annotated[str, Query()]):
    _INTEGRATIONS["gmail"].update(
        {
            "account": "[email protected]",
            "last_sync_at": datetime.now(UTC).isoformat(),
            "status": "connected",
        }
    )
    return RedirectResponse(url="/tracking?connected=gmail", status_code=302)


@router.post("/api/v1/integrations/gmail/disconnect", name="gmail_disconnect")
async def gmail_disconnect():
    _INTEGRATIONS["gmail"].update({"account": None, "status": "not_connected"})
    response = Response(status_code=204)
    response.headers["HX-Redirect"] = "/tracking"
    return response


@router.get("/api/v1/integrations/{provider}/connect", name="integration_connect")
async def integration_connect(
    provider: Literal["outlook", "calendar"],
):
    callback, _ = _provider_routes(provider)
    return RedirectResponse(url=callback, status_code=302)


@router.get("/api/v1/integrations/{provider}/callback", name="integration_callback")
async def integration_callback(
    provider: Literal["outlook", "calendar"],
    code: Annotated[str, Query()],
):
    _INTEGRATIONS[provider].update(
        {
            "account": f"shyam@{provider}.test",
            "last_sync_at": datetime.now(UTC).isoformat(),
            "status": "connected",
        }
    )
    return RedirectResponse(url=f"/tracking?connected={provider}", status_code=302)


@router.post("/api/v1/integrations/{provider}/disconnect", name="integration_disconnect")
async def integration_disconnect(
    provider: Literal["outlook", "calendar"],
):
    _INTEGRATIONS[provider].update({"account": None, "status": "not_connected"})
    response = Response(status_code=204)
    response.headers["HX-Redirect"] = "/tracking"
    return response
