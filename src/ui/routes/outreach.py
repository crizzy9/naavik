"""Outreach route + fragment + JSON stubs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from db.session import get_session
from models import User
from models.enums import OutreachIntent, OutreachStatus
from services import contact_tracker, outreach_service
from services.auth import require_authed_session
from ui import outreach_ctx as octx
from ui.templates_setup import templates

router = APIRouter()


def _effective_user_id(user: User | None) -> int:
    return user.id if user is not None else 1


# ─────────────────────────────────────────────────────────────────────────
# Page handler
# ─────────────────────────────────────────────────────────────────────────


@router.get("/outreach", response_class=HTMLResponse, name="outreach")
async def get_outreach(
    request: Request,
    application: Annotated[int | None, Query()] = None,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    ctx = await octx.build_outreach_ctx(
        session, user_id=_effective_user_id(user), selected_app_id=application
    )
    ctx["active_sidebar"] = "outreach"
    ctx["active_template_path"] = "/outreach"
    return templates.TemplateResponse(request, "pages/outreach.html", ctx)


# ─────────────────────────────────────────────────────────────────────────
# Fragment endpoints
# ─────────────────────────────────────────────────────────────────────────


@router.get(
    "/_fragments/outreach/app-detail/{application_id}",
    response_class=HTMLResponse,
    name="outreach_app_detail_fragment",
)
async def fragment_app_detail(
    request: Request,
    application_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    ctx = await octx.build_outreach_ctx(
        session, user_id=_effective_user_id(user), selected_app_id=application_id
    )
    if ctx.get("detail") is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return templates.TemplateResponse(request, "pages/_outreach_detail.html", ctx)


@router.post(
    "/_fragments/outreach/draft/{contact_id}",
    response_class=HTMLResponse,
    name="outreach_draft_fragment",
)
async def fragment_outreach_draft(
    request: Request,
    contact_id: int,
    application_id: Annotated[int | None, Query()] = None,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    """Return a freshly-drafted message card for a contact."""
    contact = await contact_tracker.get_contact(session, contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    body = (
        f"Hey {contact.name.split()[0]} — quick follow-up on the conversation. "
        "Happy to share an updated CV if helpful."
    )
    msg = await outreach_service.create_message(
        session,
        user_id=_effective_user_id(user),
        contact_id=contact_id,
        application_id=application_id,
        intent=OutreachIntent.FOLLOW_UP,
        body=body,
        status=OutreachStatus.DRAFT,
    )
    await session.commit()
    return templates.TemplateResponse(
        request,
        "components/outreach_message_card.html",
        {
            "message": {
                "id": msg.id,
                "body": msg.body,
                "status": msg.status.value.upper(),
                "ai_generated": True,
                "contact_name": contact.name,
                "channel": "linkedin",
                "sent_at": None,
                "responded_at": None,
            },
            "editable": True,
        },
    )


# ─────────────────────────────────────────────────────────────────────────
# JSON stubs
# ─────────────────────────────────────────────────────────────────────────


@router.get("/api/v1/contacts", name="contacts_list")
async def get_contacts(
    company: Annotated[str | None, Query()] = None,
    app_id: Annotated[int | None, Query()] = None,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    user_id = _effective_user_id(user)
    if company:
        items = await contact_tracker.list_contacts_for_company(
            session, user_id=user_id, company=company
        )
    elif app_id:
        items = await contact_tracker.list_contacts_for_application(session, app_id)
    else:
        items = await contact_tracker.list_contacts(session, user_id)
    return [c.model_dump(mode="json") for c in items]


@router.post("/api/v1/contacts", name="contacts_post")
async def post_contact(
    payload: Annotated[dict[str, Any], Body()],
    _user: User | None = Depends(require_authed_session),
):
    return {"ok": True, "id": 0, "payload": payload}


@router.get("/api/v1/contacts/{contact_id}", name="contacts_get")
async def get_contact(
    contact_id: int,
    session: AsyncSession = Depends(get_session),
):
    c = await contact_tracker.get_contact(session, contact_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    return c.model_dump(mode="json")


@router.put("/api/v1/contacts/{contact_id}", name="contacts_put")
async def put_contact(
    contact_id: int,
    payload: Annotated[dict[str, Any], Body()],
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
):
    c = await contact_tracker.get_contact(session, contact_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    return {"ok": True, "id": contact_id}


@router.delete("/api/v1/contacts/{contact_id}", name="contacts_delete")
async def delete_contact(
    contact_id: int,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
):
    c = await contact_tracker.get_contact(session, contact_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    c.deleted_at = datetime.now(UTC)
    session.add(c)
    await session.commit()
    return Response(status_code=204)


@router.post("/api/v1/contacts/find", name="contacts_find")
async def post_contacts_find(
    payload: Annotated[dict[str, Any], Body()],
    _user: User | None = Depends(require_authed_session),
):
    """Stub LinkedIn search — return 3 hardcoded fake contacts."""
    company = payload.get("company", "Unknown")
    fake = [
        {
            "id": 9001,
            "name": "Alex Chen",
            "title": "Senior Engineer",
            "company": company,
            "linkedin_degree": "2nd · via Daniel",
            "relationship": "cold",
        },
        {
            "id": 9002,
            "name": "Maya Singh",
            "title": "Engineering Manager",
            "company": company,
            "linkedin_degree": "3rd",
            "relationship": "cold",
        },
        {
            "id": 9003,
            "name": "Tom Williams",
            "title": "Recruiter",
            "company": company,
            "linkedin_degree": "2nd",
            "relationship": "cold",
        },
    ]
    return fake


@router.get("/api/v1/outreach/messages", name="outreach_messages_list")
async def get_outreach_messages(
    app_id: Annotated[int | None, Query()] = None,
    contact_id: Annotated[int | None, Query()] = None,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    if app_id:
        msgs = await outreach_service.list_messages_for_application(session, app_id)
    elif contact_id:
        msgs = await outreach_service.list_messages_for_contact(session, contact_id)
    else:
        msgs = await outreach_service.list_all_messages(session, _effective_user_id(user))
    return [m.model_dump(mode="json") for m in msgs]


@router.post("/api/v1/outreach/draft", name="outreach_draft_post")
async def post_outreach_draft(
    payload: Annotated[dict[str, Any], Body()],
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    contact_id = int(payload.get("contact_id", 0))
    app_id = payload.get("app_id")
    intent_str = payload.get("intent", "follow_up")
    try:
        intent = OutreachIntent(intent_str)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unknown intent {intent_str!r}") from None
    contact = await contact_tracker.get_contact(session, contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    body = (
        f"Hey {contact.name.split()[0]} — quick check-in. Let me know if there's "
        "anything I can do to help move things along."
    )
    msg = await outreach_service.create_message(
        session,
        user_id=_effective_user_id(user),
        contact_id=contact_id,
        application_id=app_id,
        intent=intent,
        body=body,
        status=OutreachStatus.DRAFT,
    )
    await session.commit()
    return msg.model_dump(mode="json")


@router.post("/api/v1/outreach/send", name="outreach_send")
async def post_outreach_send(
    payload: Annotated[dict[str, Any], Body()],
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
):
    msg_id = int(payload.get("message_id", 0))
    msg = await outreach_service.mark_sent(session, msg_id)
    if msg is None:
        raise HTTPException(status_code=404, detail="Message not found")
    await session.commit()
    return msg.model_dump(mode="json")


@router.post("/api/v1/outreach/skip", name="outreach_skip")
async def post_outreach_skip(
    payload: Annotated[dict[str, Any], Body()],
    _user: User | None = Depends(require_authed_session),
):
    return Response(status_code=204)
