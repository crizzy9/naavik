"""Email thread JSON endpoints (BACKEND.md § D.5)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from db import sample_data as sd
from models import User
from models.enums import EmailClassification
from services.auth import require_authed_session

router = APIRouter()


@router.get("/api/v1/email/threads", name="email_threads_list")
async def get_email_threads(
    app_id: Annotated[int | None, Query()] = None,
    classification: Annotated[str | None, Query()] = None,
):
    threads = await sd.get_email_threads()
    if app_id is not None:
        threads = [t for t in threads if t.application_id == app_id]
    if classification:
        try:
            cls = EmailClassification(classification.lower())
        except ValueError:
            raise HTTPException(status_code=422, detail="Unknown classification") from None
        threads = [t for t in threads if t.classification == cls]
    return [t.model_dump(mode="json") for t in threads]


@router.get("/api/v1/email/threads/{thread_id}", name="email_thread_get")
async def get_email_thread(thread_id: int):
    t = await sd.get_email_thread(thread_id)
    if t is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    return t.model_dump(mode="json")


@router.post("/api/v1/email/threads/{thread_id}/draft-reply", name="email_thread_draft_reply")
async def post_email_thread_draft_reply(
    thread_id: int,
    payload: Annotated[dict[str, Any] | None, Body()] = None,
    _user: User | None = Depends(require_authed_session),
):
    t = await sd.get_email_thread(thread_id)
    if t is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    intent = (payload or {}).get("intent", "follow_up")
    return {
        "thread_id": thread_id,
        "intent": intent,
        "body": (
            "Thanks for the follow-up — I'm available next week any afternoon "
            "PT to chat further. Let me know what works on your end."
        ),
    }
