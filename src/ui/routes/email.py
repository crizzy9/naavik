"""Email thread JSON endpoints (BACKEND.md § D.5) + email-suggestion seam.

Plan 90 (0.5.0.03) adds the human-confirm apply/dismiss routes onto
`/api/v1/applications/{id}/...`. Mounting them here (vs `api/applications.py`)
keeps the email surfaces co-located.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlmodel.ext.asyncio.session import AsyncSession

from api.auth import require_csrf
from db.session import get_session
from models import User
from models.enums import EmailClassification
from services import application_service, email_service
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
    _csrf: None = Depends(require_csrf),
):
    t = await email_service.get_thread(session, thread_id)
    if t is None or t.user_id != _effective_user_id(user):
        raise HTTPException(status_code=404, detail="Thread not found")
    intent = (payload or {}).get("intent", "follow_up")
    # Plan 90 / 0.5.0.06 — graceful no-LLM degrade via the dedicated draft
    # prompt. JSON-only response; auto-send wire deferred to 0.5.0.06b.
    from sqlmodel import select as _select

    from llm import LLMProviderError, get_provider
    from llm.prompts.draft_email_response import draft_email_response
    from models import Settings

    settings = (
        await session.exec(_select(Settings).where(Settings.user_id == _effective_user_id(user)))
    ).one_or_none()
    fallback = {
        "thread_id": thread_id,
        "intent": intent,
        "subject": f"Re: {t.subject}" if t.subject else "Re:",
        "body": (
            "Thanks for the note — I'll get back to you shortly with a fuller "
            "reply once I have a moment to read this carefully."
        ),
        "model": None,
        "llm_configured": False,
    }
    if settings is None:
        return fallback
    try:
        provider = get_provider(settings)
    except LLMProviderError as exc:
        if exc.kind == "auth_required":
            return fallback
        raise
    try:
        drafted = await draft_email_response(
            provider,
            session=session,
            user_id=_effective_user_id(user),
            subject=t.subject,
            sender=(t.messages[0].get("sender") if t.messages else None) or "the recipient",
            recent_snippet=(t.messages[0].get("snippet") if t.messages else None) or "",
            intent=intent,
        )
    except Exception:  # noqa: BLE001
        return fallback
    return {
        "thread_id": thread_id,
        "intent": intent,
        "subject": drafted.subject,
        "body": drafted.body,
        "model": getattr(provider, "model", None) or getattr(provider, "model_name", None),
        "llm_configured": True,
    }


# ── Email-suggestion apply/dismiss seam (plan 90 / 0.5.0.03) ────────────


@router.post(
    "/api/v1/applications/{app_id}/email-suggestion/{message_id}/apply",
    name="application_apply_email_suggestion",
)
async def apply_email_suggestion(
    app_id: int,
    message_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    try:
        app = await application_service.apply_email_suggestion(
            session,
            application_id=app_id,
            message_id=message_id,
            user_id=_effective_user_id(user),
        )
    except application_service.ApplicationServiceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    return {
        "application_id": app.id,
        "status": app.status.value,
        "closed_reason": app.closed_reason.value if app.closed_reason else None,
    }


@router.post(
    "/api/v1/applications/{app_id}/email-suggestion/{message_id}/dismiss",
    name="application_dismiss_email_suggestion",
)
async def dismiss_email_suggestion(
    app_id: int,
    message_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    try:
        await application_service.dismiss_email_suggestion(
            session,
            application_id=app_id,
            message_id=message_id,
            user_id=_effective_user_id(user),
        )
    except application_service.ApplicationServiceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    return {"status": "dismissed", "message_id": message_id}
