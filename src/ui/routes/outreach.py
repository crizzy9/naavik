"""Outreach route + fragment + JSON stubs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse

from db import sample_data as sd
from models.enums import OutreachIntent, OutreachStatus
from ui import outreach_ctx as octx
from ui.templates_setup import templates

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────
# Page handler
# ─────────────────────────────────────────────────────────────────────────


@router.get("/outreach", response_class=HTMLResponse, name="outreach")
async def get_outreach(
    request: Request,
    application: Annotated[int | None, Query()] = None,
):
    ctx = await octx.build_outreach_ctx(selected_app_id=application)
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
async def fragment_app_detail(request: Request, application_id: int):
    ctx = await octx.build_outreach_ctx(selected_app_id=application_id)
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
):
    """Return a freshly-drafted message card for a contact."""
    contact = await sd.get_contact(contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    body = (
        f"Hey {contact.name.split()[0]} — quick follow-up on the conversation. "
        "Happy to share an updated CV if helpful."
    )
    msg = await sd._append_outreach_message(
        contact_id=contact_id,
        application_id=application_id,
        intent=OutreachIntent.FOLLOW_UP,
        body=body,
        status=OutreachStatus.DRAFT,
    )
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
):
    if company:
        items = await sd.contacts_for_company(company)
    elif app_id:
        items = await sd.contacts_for_application(app_id)
    else:
        items = await sd.get_contacts()
    return [c.model_dump(mode="json") for c in items]


@router.post("/api/v1/contacts", name="contacts_post")
async def post_contact(payload: Annotated[dict[str, Any], Body()]):
    return {"ok": True, "id": sd._next_id(sd.CONTACTS), "payload": payload}


@router.get("/api/v1/contacts/{contact_id}", name="contacts_get")
async def get_contact(contact_id: int):
    c = await sd.get_contact(contact_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    return c.model_dump(mode="json")


@router.put("/api/v1/contacts/{contact_id}", name="contacts_put")
async def put_contact(contact_id: int, payload: Annotated[dict[str, Any], Body()]):
    c = await sd.get_contact(contact_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    return {"ok": True, "id": contact_id}


@router.delete("/api/v1/contacts/{contact_id}", name="contacts_delete")
async def delete_contact(contact_id: int):
    c = await sd.get_contact(contact_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    c.deleted_at = datetime.now(UTC)
    return Response(status_code=204)


@router.post("/api/v1/contacts/find", name="contacts_find")
async def post_contacts_find(payload: Annotated[dict[str, Any], Body()]):
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
):
    if app_id:
        msgs = await sd.outreach_messages_for_application(app_id)
    elif contact_id:
        msgs = await sd.outreach_messages_for_contact(contact_id)
    else:
        msgs = sd.OUTREACH_MESSAGES
    return [m.model_dump(mode="json") for m in msgs]


@router.post("/api/v1/outreach/draft", name="outreach_draft_post")
async def post_outreach_draft(payload: Annotated[dict[str, Any], Body()]):
    contact_id = int(payload.get("contact_id", 0))
    app_id = payload.get("app_id")
    intent_str = payload.get("intent", "follow_up")
    try:
        intent = OutreachIntent(intent_str)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unknown intent {intent_str!r}") from None
    contact = await sd.get_contact(contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    body = (
        f"Hey {contact.name.split()[0]} — quick check-in. Let me know if there's "
        "anything I can do to help move things along."
    )
    msg = await sd._append_outreach_message(
        contact_id=contact_id,
        application_id=app_id,
        intent=intent,
        body=body,
        status=OutreachStatus.DRAFT,
    )
    return msg.model_dump(mode="json")


@router.post("/api/v1/outreach/send", name="outreach_send")
async def post_outreach_send(payload: Annotated[dict[str, Any], Body()]):
    msg_id = int(payload.get("message_id", 0))
    msg = next((m for m in sd.OUTREACH_MESSAGES if m.id == msg_id), None)
    if msg is None:
        raise HTTPException(status_code=404, detail="Message not found")
    msg.status = OutreachStatus.SENT
    msg.sent_at = datetime.now(UTC)
    msg.updated_at = datetime.now(UTC)
    return msg.model_dump(mode="json")


@router.post("/api/v1/outreach/skip", name="outreach_skip")
async def post_outreach_skip(payload: Annotated[dict[str, Any], Body()]):
    return Response(status_code=204)
