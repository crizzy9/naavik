"""Email thread JSON endpoints (BACKEND.md § D.5) + email-suggestion seam.

Plan 90 (0.5.0.03) adds the human-confirm apply/dismiss routes onto
`/api/v1/applications/{id}/...`. Mounting them here (vs `api/applications.py`)
keeps the email surfaces co-located.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Form, HTTPException, Query, Request, Response
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


# ── On-demand full body (plan 95 § 3.9.1 B) ─────────────────────────────


@router.post("/api/v1/email/messages/{message_id}/body", name="email_message_body")
async def post_email_message_body(
    message_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    """Fetch one message's full body live over IMAP (BODY.PEEK by stored
    UID). The body transits memory only — NEVER persisted; the at-rest
    posture stays snippet-only. Returns an HTML fragment for the chain's
    expand slot."""
    from fastapi.responses import HTMLResponse
    from markupsafe import escape

    from models import EmailAccount, EmailMessage
    from services.email import sync as email_sync

    msg = await session.get(EmailMessage, message_id)
    if msg is None or msg.user_id != _effective_user_id(user):
        raise HTTPException(status_code=404, detail="No such email message")
    fallback = (
        '<p class="text-xs text-slate-500" data-testid="body-unavailable">'
        "Full text isn't fetchable for this message — use the provider link above.</p>"
    )
    if not msg.imap_uid or msg.account_id is None:
        return HTMLResponse(fallback)
    account = await session.get(EmailAccount, msg.account_id)
    if account is None or account.user_id != msg.user_id:
        return HTMLResponse(fallback)

    body = await email_sync.fetch_message_body(account, uid=msg.imap_uid)
    if not body:
        return HTMLResponse(fallback)
    return HTMLResponse(
        '<div class="mt-1 max-h-64 overflow-y-auto rounded-md bg-slate-950/70 px-2.5 py-2 '
        'text-xs text-slate-300 leading-relaxed whitespace-pre-wrap" '
        f'data-testid="message-body-{message_id}">{escape(body)}</div>'
    )


@router.post(
    "/api/v1/integrations/email/{account_id}/body-excerpt",
    name="email_account_body_excerpt_toggle",
)
async def post_email_account_body_excerpt(
    account_id: int,
    enabled: Annotated[int, Form()] = 0,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    """Per-account § 3.9.1 opt-in toggle (default OFF). Applies to newly
    synced mail only — already-synced messages keep snippet-only."""
    from datetime import UTC, datetime

    from models import EmailAccount

    account = await session.get(EmailAccount, account_id)
    if account is None or account.user_id != _effective_user_id(user):
        raise HTTPException(status_code=404, detail="No such account")
    account.store_body_excerpt = bool(enabled)
    account.updated_at = datetime.now(UTC)
    session.add(account)
    await session.commit()
    response = Response(status_code=204)
    response.headers["HX-Trigger"] = json.dumps(
        {
            "showToast": {
                "tone": "info",
                "text": (
                    "Storing 2,000-char body excerpts for new mail."
                    if account.store_body_excerpt
                    else "Back to snippet-only storage."
                ),
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
    request: Request,
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
    if request.headers.get("HX-Request"):
        # Plan 95 § 3.9 — mounted inline on the conversation section; the
        # board position + timeline change, so refresh IS the feedback.
        response = Response(status_code=204)
        response.headers["HX-Refresh"] = "true"
        return response
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
    request: Request,
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
    if request.headers.get("HX-Request"):
        response = Response(status_code=204)
        response.headers["HX-Trigger"] = json.dumps(
            {"showToast": {"tone": "info", "text": "Suggestion dismissed."}}
        )
        return response
    return {"status": "dismissed", "message_id": message_id}
