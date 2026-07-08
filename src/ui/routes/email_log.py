"""/emails — the first-class email log (plan 96b, owner decision #4/#14).

64 % of synced mail had no surface at all before this page: unlinked
non-signal mail and any unclassified backlog appeared nowhere. The log
shows EVERYTHING the sync brought in, its classification, its link state,
and what it did to the pipeline — with the correction affordances
(reclassify / flag sender) mounted on every row.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from db.session import get_session
from models import User
from services.auth import require_authed_session
from ui import email_log_ctx
from ui.templates_setup import templates

router = APIRouter()


def _effective_user_id(user: User | None) -> int:
    return user.id if user is not None else 1


def _coerce_account_id(raw: str) -> int | None:
    """The filter form submits `account_id=` (empty) when no account is
    picked — an int-typed Query would 422 on it."""
    try:
        return int(raw) if raw else None
    except ValueError:
        return None


@router.get("/emails", response_class=HTMLResponse, name="email_log")
async def get_email_log(
    request: Request,
    classification: Annotated[str, Query(max_length=40)] = "",
    link_state: Annotated[str, Query(max_length=20)] = "",
    account_id: Annotated[str, Query(max_length=12)] = "",
    date_from: Annotated[str, Query(max_length=10)] = "",
    date_to: Annotated[str, Query(max_length=10)] = "",
    sender_q: Annotated[str, Query(max_length=160)] = "",
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    ctx = await email_log_ctx.build_email_log_ctx(
        session,
        user_id=_effective_user_id(user),
        classification=classification or None,
        link_state=link_state or None,
        account_id=_coerce_account_id(account_id),
        date_from=date_from or None,
        date_to=date_to or None,
        sender_q=sender_q or None,
    )
    ctx["active_sidebar"] = "emails"
    ctx["active_template_path"] = "/emails"
    return templates.TemplateResponse(request, "pages/email/email_log.html", ctx)


@router.get("/_fragments/email/log", response_class=HTMLResponse, name="email_log_fragment")
async def fragment_email_log(
    request: Request,
    classification: Annotated[str, Query(max_length=40)] = "",
    link_state: Annotated[str, Query(max_length=20)] = "",
    account_id: Annotated[str, Query(max_length=12)] = "",
    date_from: Annotated[str, Query(max_length=10)] = "",
    date_to: Annotated[str, Query(max_length=10)] = "",
    sender_q: Annotated[str, Query(max_length=160)] = "",
    cursor: Annotated[str, Query(max_length=64)] = "",
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    """One keyset page — filter swaps (no cursor) and load-more appends
    (cursor) share this response; granularity matches #email-log-list."""
    ctx = await email_log_ctx.build_email_log_ctx(
        session,
        user_id=_effective_user_id(user),
        classification=classification or None,
        link_state=link_state or None,
        account_id=_coerce_account_id(account_id),
        date_from=date_from or None,
        date_to=date_to or None,
        sender_q=sender_q or None,
        cursor=cursor or None,
    )
    return templates.TemplateResponse(request, "components/email/_email_log_page.html", ctx)
