"""Email thread JSON endpoints (BACKEND.md § D.5)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlmodel.ext.asyncio.session import AsyncSession

from db.session import get_session
from models import User
from models.enums import EmailClassification
from services import email_service
from services.auth import require_authed_session

router = APIRouter()


def _effective_user_id(user: User | None) -> int:
    return user.id if user is not None else 1


@router.get("/api/v1/email/threads", name="email_threads_list")
async def get_email_threads(
    app_id: Annotated[int | None, Query()] = None,
    classification: Annotated[str | None, Query()] = None,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    cls: EmailClassification | None = None
    if classification:
        try:
            cls = EmailClassification(classification.lower())
        except ValueError:
            raise HTTPException(status_code=422, detail="Unknown classification") from None
    threads = await email_service.list_threads(
        session,
        _effective_user_id(user),
        application_id=app_id,
        classification=cls,
    )
    return [t.model_dump(mode="json") for t in threads]


@router.get("/api/v1/email/threads/{thread_id}", name="email_thread_get")
async def get_email_thread(
    thread_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    t = await email_service.get_thread(session, thread_id)
    if t is None or t.user_id != _effective_user_id(user):
        raise HTTPException(status_code=404, detail="Thread not found")
    return t.model_dump(mode="json")


@router.post("/api/v1/email/threads/{thread_id}/draft-reply", name="email_thread_draft_reply")
async def post_email_thread_draft_reply(
    thread_id: int,
    payload: Annotated[dict[str, Any] | None, Body()] = None,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    t = await email_service.get_thread(session, thread_id)
    if t is None or t.user_id != _effective_user_id(user):
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
