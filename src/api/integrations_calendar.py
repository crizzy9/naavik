"""Calendar (secret ICS URL) integration routes — item 11 (2026-07).

Mirrors the Gmail one-screen pattern: one card, one field, validated +
fetched server-side BEFORE saving, first sync inline, honest fragments +
toasts for every outcome. Read-only; event creation is a future OAuth
follow-up (docs/design/EMAIL_MONITORING.md § Calendar).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from api.auth import require_csrf
from db.session import get_session
from models import CalendarConnection, User
from services.auth import require_authed_session
from services.email import calendar_sync

log = logging.getLogger(__name__)

router = APIRouter()


def _effective_user_id(user: User | None) -> int:
    return user.id if user is not None else 1


def _error_fragment(message: str, status_code: int = 422) -> HTMLResponse:
    from markupsafe import escape

    return HTMLResponse(
        f'<div class="text-sm text-rose-300">{escape(message)}</div>', status_code=status_code
    )


@router.post("/api/v1/integrations/calendar", name="api_calendar_connect")
async def connect_calendar(
    ics_url: Annotated[str, Form()],
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
) -> HTMLResponse:
    user_id = _effective_user_id(_user)
    url = (ics_url or "").strip()

    ok, reason = calendar_sync.validate_ics_url(url)
    if not ok:
        log.info("calendar connect rejected for user %s: %s", user_id, reason)
        return _error_fragment(calendar_sync.SAFE_URL_ERROR)

    # Fetch + parse BEFORE saving anything — same test-before-save contract
    # as the Gmail connect.
    try:
        body = await calendar_sync.fetch_ics(url)
        calendar_sync.parse_ics(body)  # parse errors → honest connect failure
    except Exception as exc:  # noqa: BLE001 — user-facing connect must not 500
        log.info("calendar connect fetch failed for user %s: %s", user_id, exc)
        return _error_fragment(
            "Couldn't fetch that address. Copy the FULL “Secret address in iCal "
            "format” from Google Calendar → Settings → your calendar → "
            "“Integrate calendar”."
        )
    if not body.lstrip().startswith("BEGIN:VCALENDAR"):
        return _error_fragment(
            "That URL responded, but not with a calendar (.ics) file — double-check "
            "you copied the secret iCal address, not the calendar's public page."
        )

    connection = await calendar_sync.get_connection(session, user_id)
    if connection is None:
        connection = CalendarConnection(user_id=user_id, ics_url_encrypted="")
    calendar_sync.store_ics_url(connection, url)
    connection.status = "ok"
    connection.last_error = None
    connection.updated_at = datetime.now(UTC)
    session.add(connection)
    await session.flush()

    total, new = await calendar_sync.sync_connection(session, connection)
    await session.commit()

    response = HTMLResponse(
        '<div class="text-sm text-emerald-300">'
        f"Calendar connected — {total} event{'s' if total != 1 else ''} in the next "
        f"60 days ({new} new). Syncs every 45 minutes.</div>"
    )
    response.headers["HX-Trigger"] = json.dumps(
        {
            "calendarConnected": True,
            "showToast": {
                "tone": "success",
                "text": f"Calendar connected — {total} upcoming events synced.",
            },
        }
    )
    return response


@router.post("/api/v1/integrations/calendar/sync-now", name="api_calendar_sync_now")
async def sync_calendar_now(
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
) -> HTMLResponse:
    user_id = _effective_user_id(_user)
    connection = await calendar_sync.get_connection(session, user_id)
    if connection is None:
        raise HTTPException(status_code=404, detail="No calendar connected")
    total, new = await calendar_sync.sync_connection(session, connection)
    await session.commit()
    response = HTMLResponse("")
    if connection.status == "ok":
        toast = {
            "tone": "success",
            "text": f"Calendar synced — {total} events in window, {new} new.",
        }
    else:
        toast = {
            "tone": "warning",
            "text": f"Calendar sync failed — {connection.last_error or 'check the ICS address'}.",
        }
    response.headers["HX-Trigger"] = json.dumps({"showToast": toast})
    return response


@router.delete("/api/v1/integrations/calendar", name="api_calendar_disconnect")
async def disconnect_calendar(
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
) -> HTMLResponse:
    """200 + empty body (htmx swaps the card away; 204 would be ignored) + toast."""
    from sqlmodel import delete as sql_delete

    from models import CalendarEvent

    user_id = _effective_user_id(_user)
    connection = await calendar_sync.get_connection(session, user_id)
    if connection is None:
        raise HTTPException(status_code=404, detail="No calendar connected")
    connection.deleted_at = datetime.now(UTC)
    connection.updated_at = datetime.now(UTC)
    session.add(connection)
    await session.exec(sql_delete(CalendarEvent).where(CalendarEvent.user_id == user_id))
    await session.commit()
    response = HTMLResponse("")
    response.headers["HX-Trigger"] = json.dumps(
        {
            "showToast": {
                "tone": "success",
                "text": "Calendar disconnected — synced events removed.",
            }
        }
    )
    return response
