"""Email thread JSON endpoints (BACKEND.md § D.5) + email-suggestion seam.

Plan 90 (0.5.0.03) adds the human-confirm apply/dismiss routes onto
`/api/v1/applications/{id}/...`. Mounting them here (vs `api/applications.py`)
keeps the email surfaces co-located.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Form, HTTPException, Query, Response
from sqlmodel.ext.asyncio.session import AsyncSession

from api.auth import require_csrf
from db.session import get_session
from models import User
from models.enums import EmailClassification
from services import applications
from services import email as email_service
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
    from api.deps import owned_email_thread_or_404

    t = await owned_email_thread_or_404(session, thread_id, _effective_user_id(user))
    return t.model_dump(mode="json")


@router.post("/api/v1/email/threads/{thread_id}/draft-reply", name="email_thread_draft_reply")
async def post_email_thread_draft_reply(
    thread_id: int,
    payload: Annotated[dict[str, Any] | None, Body()] = None,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    from api.deps import owned_email_thread_or_404

    t = await owned_email_thread_or_404(session, thread_id, _effective_user_id(user))
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


# ── Correction affordances (plan 95 § 3.4) ──────────────────────────────


@router.post("/api/v1/email/messages/{message_id}/reclassify", name="email_message_reclassify")
async def post_email_message_reclassify(
    message_id: int,
    classification: Annotated[str, Form(min_length=1, max_length=40)],
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    try:
        target = EmailClassification(classification.strip().lower())
    except ValueError:
        raise HTTPException(status_code=422, detail="Unknown classification") from None
    from services.email import corrections

    try:
        await corrections.reclassify_message(
            session,
            user_id=_effective_user_id(user),
            message_id=message_id,
            to_classification=target,
        )
    except corrections.CorrectionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    # Full refresh: the relabel can move a group's derived stage, close
    # suggestions, or relink — the board state change IS the feedback.
    response = Response(status_code=204)
    response.headers["HX-Refresh"] = "true"
    return response


@router.post("/api/v1/email/threads/{thread_id}/unlink", name="email_thread_unlink")
async def post_email_thread_unlink(
    thread_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    from services.email import corrections

    try:
        n = await corrections.unlink_thread(
            session, user_id=_effective_user_id(user), thread_id=thread_id
        )
    except corrections.CorrectionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    response = Response(status_code=204)
    response.headers["HX-Trigger"] = json.dumps(
        {
            "showToast": {
                "tone": "info",
                "text": f"Unlinked {n} email{'s' if n != 1 else ''} from this application.",
            }
        }
    )
    return response


# ── Sender flags (plan 95 § 3.3) ────────────────────────────────────────


@router.post("/api/v1/email/senders/flag", name="email_sender_flag")
async def post_email_sender_flag(
    domain: Annotated[str, Form(min_length=3, max_length=254)],
    treatment: Annotated[str, Form(min_length=1, max_length=20)],
    from_message_id: Annotated[int | None, Form()] = None,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    """ "Flag sender…" — Agency / Not job-related / Actually an employer.

    Persists the `SenderRule` (user rule > seed > LLM forever after) and
    retroactively re-treats the domain's already-classified mail.
    """
    from services.email import sender_rules

    try:
        await sender_rules.flag_sender(
            session,
            user_id=_effective_user_id(user),
            domain=domain,
            treatment=treatment,
            from_message_id=from_message_id,
        )
    except sender_rules.SenderRuleError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await session.commit()
    # Full refresh: flagged groups leave the panel / move sections.
    response = Response(status_code=204)
    response.headers["HX-Refresh"] = "true"
    return response


# ── Email-suggestion apply/dismiss seam (plan 90 / 0.5.0.03) ────────────


@router.post(
    "/api/v1/applications/{app_id}/email-suggestion/{message_id}/apply",
    name="application_apply_email_suggestion",
)
async def apply_email_suggestion(
    app_id: int,
    message_id: int,
    resume: Annotated[int, Query()] = 0,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    try:
        app = await applications.apply_email_suggestion(
            session,
            application_id=app_id,
            message_id=message_id,
            user_id=_effective_user_id(user),
        )
        # Plan 95 § 3.8.6 — "Apply & resume auto-tracking": accepting the
        # machine's next call is the natural signal the earlier objection
        # no longer applies; one click does both.
        if resume:
            await applications.clear_pin(
                session, user_id=_effective_user_id(user), application_id=app_id
            )
    except applications.ApplicationServiceError as exc:
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
        await applications.dismiss_email_suggestion(
            session,
            application_id=app_id,
            message_id=message_id,
            user_id=_effective_user_id(user),
        )
    except applications.ApplicationServiceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    return {"status": "dismissed", "message_id": message_id}
