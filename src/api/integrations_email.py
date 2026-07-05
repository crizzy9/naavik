"""Email integration routes — plan 90 (0.5.0.01).

Connect IMAP, list accounts, test connection, soft-delete account, sync-now.

Security posture mirrors the 0.7.0.48 fix cycle (commits d0e815d/3514b9d):
- Every state-changing route guards CSRF via `Depends(require_csrf)`.
- Every per-user write resolves owner via `_effective_user_id` — NO hardcoded
  user_id=1.
- IMAP password is NEVER echoed in any response shape. `EmailAccountRead`
  strips the column server-side.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, EmailStr
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from api.auth import require_csrf
from db.session import get_session
from models import EmailAccount, EmailAccountStatus, User
from models.enums import EmailAccountProvider
from services import email as email_sync
from services.auth import require_authed_session
from services.email import credentials as email_credentials
from services.email import imap_host_guard
from services.rate_limit import check_email_sync_now_rate_limit
from ui.routes.profile import _effective_user_id

log = logging.getLogger(__name__)

router = APIRouter()


class EmailAccountRead(BaseModel):
    """API-safe view — password column NEVER surfaces."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    provider: EmailAccountProvider
    account_email: EmailStr
    imap_host: str
    imap_port: int
    imap_username: str
    imap_use_tls: bool
    status: EmailAccountStatus
    last_sync_at: datetime | None = None
    connection_failure_count: int
    last_error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class TestConnectionResult(BaseModel):
    ok: bool
    error: str | None = None


@router.get("/api/v1/integrations/email", name="api_email_accounts_list")
async def list_email_accounts(
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
) -> list[EmailAccountRead]:
    user_id = _effective_user_id(_user)
    rows = (
        await session.exec(
            select(EmailAccount).where(
                EmailAccount.user_id == user_id,
                EmailAccount.deleted_at.is_(None),
            )
        )
    ).all()
    return [EmailAccountRead.model_validate(r) for r in rows]


async def _upsert_imap_account(
    session: AsyncSession,
    *,
    user_id: int,
    account_email: str,
    imap_host: str,
    imap_port: int,
    imap_username: str,
    imap_password: str,
    imap_use_tls: bool,
) -> EmailAccount:
    """Create-or-refresh the EmailAccount row (credential Fernet-encrypted)."""
    existing = (
        await session.exec(
            select(EmailAccount).where(
                EmailAccount.user_id == user_id,
                EmailAccount.provider == EmailAccountProvider.IMAP,
                EmailAccount.account_email == account_email,
            )
        )
    ).one_or_none()
    if existing is not None:
        email_credentials.store_imap_password(existing, imap_password)
        existing.imap_host = imap_host
        existing.imap_port = imap_port
        existing.imap_username = imap_username
        existing.imap_use_tls = imap_use_tls
        existing.status = EmailAccountStatus.OK
        existing.connection_failure_count = 0
        existing.last_error_message = None
        existing.deleted_at = None
        existing.updated_at = datetime.now(UTC)
        session.add(existing)
        await session.flush()
        return existing

    account = EmailAccount(
        user_id=user_id,
        provider=EmailAccountProvider.IMAP,
        account_email=account_email,
        imap_host=imap_host,
        imap_port=imap_port,
        imap_username=imap_username,
        imap_password="",
        imap_use_tls=imap_use_tls,
        status=EmailAccountStatus.OK,
    )
    email_credentials.store_imap_password(account, imap_password)
    session.add(account)
    await session.flush()
    return account


@router.post("/api/v1/integrations/email/imap", name="api_email_account_connect")
async def connect_imap(
    request: Request,
    account_email: Annotated[EmailStr, Form()],
    imap_host: Annotated[str, Form()],
    imap_username: Annotated[str, Form()],
    imap_password: Annotated[str, Form()],
    imap_port: Annotated[int, Form()] = 993,
    imap_use_tls: Annotated[bool, Form()] = True,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    is_htmx = request.headers.get("hx-request") == "true"

    def _fail(message: str) -> HTMLResponse:
        # HTMX callers get a visible inline fragment (hx-target-error slot);
        # JSON callers keep the 400 detail shape.
        if is_htmx:
            from markupsafe import escape

            return HTMLResponse(
                f'<div class="text-sm text-rose-300">{escape(message)}</div>',
                status_code=400,
            )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)

    user_id = _effective_user_id(_user)

    # SSRF guard: reject internal / disallowed-port targets before any
    # connection attempt (PR #214 hacker H1). The connection helpers re-check
    # at every connect + sync for DNS-rebind TOCTOU defense.
    host_ok, _reason = imap_host_guard.check_imap_host(imap_host, imap_port)
    if not host_ok:
        return _fail(imap_host_guard.SAFE_ERROR_MESSAGE)

    ok, err = await email_sync.test_imap_connection(
        host=imap_host,
        port=imap_port,
        username=imap_username,
        password=imap_password,
    )
    if not ok:
        return _fail(err or "Could not connect to the mail server.")

    account = await _upsert_imap_account(
        session,
        user_id=user_id,
        account_email=str(account_email),
        imap_host=imap_host,
        imap_port=imap_port,
        imap_username=imap_username,
        imap_password=imap_password,
        imap_use_tls=imap_use_tls,
    )
    await session.commit()
    if is_htmx:
        # The result div used to receive raw JSON text for a flash before the
        # reload — return a readable fragment + toast instead.
        import json as _json

        response = HTMLResponse(
            '<div class="text-sm text-emerald-300">'
            f"Connected {account.account_email} — inbox tracking is live.</div>"
        )
        response.headers["HX-Trigger"] = _json.dumps(
            {
                "emailConnected": True,
                "showToast": {
                    "tone": "success",
                    "text": f"IMAP connected — {account.account_email}.",
                },
            }
        )
        return response
    return EmailAccountRead.model_validate(account)


GMAIL_IMAP_HOST = "imap.gmail.com"
GMAIL_IMAP_PORT = 993


@router.post("/api/v1/integrations/email/gmail", name="api_email_account_connect_gmail")
async def connect_gmail(
    account_email: Annotated[EmailStr, Form()],
    app_password: Annotated[str, Form()],
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
) -> HTMLResponse:
    """One-screen Gmail connect — the user types their address + app password;
    host/port/TLS/username are derived. Tests the connection BEFORE saving,
    then runs the first sync immediately and reports the result inline.

    Returns HTML fragments (the Gmail card swaps them in place):
    - 200 with a success summary (+ HX-Trigger page refresh) on connect;
    - 422 with a crisp, actionable error otherwise.
    """
    import json as _json

    user_id = _effective_user_id(_user)
    # Google renders app passwords as "xxxx xxxx xxxx xxxx" — accept the
    # pasted form with spaces.
    password = app_password.replace(" ", "").strip()
    if len(password) != 16:
        return HTMLResponse(
            '<div class="text-sm text-rose-300">That doesn\'t look like a Google app '
            "password (16 letters). Paste the code exactly as Google shows it — "
            "spaces are fine.</div>",
            status_code=422,
        )

    ok, err = await email_sync.test_imap_connection(
        host=GMAIL_IMAP_HOST,
        port=GMAIL_IMAP_PORT,
        username=str(account_email),
        password=password,
    )
    if not ok:
        hint = (
            "Check that 2-Step Verification is on and the app password was "
            "created for this exact Google account."
        )
        return HTMLResponse(
            f'<div class="text-sm text-rose-300">Connection failed: {err or "login rejected"}.'
            f' <span class="text-slate-400">{hint}</span></div>',
            status_code=422,
        )

    account = await _upsert_imap_account(
        session,
        user_id=user_id,
        account_email=str(account_email),
        imap_host=GMAIL_IMAP_HOST,
        imap_port=GMAIL_IMAP_PORT,
        imap_username=str(account_email),
        imap_password=password,
        imap_use_tls=True,
    )
    await session.commit()

    # First sync right away — the user sees data flowing before leaving the
    # page instead of waiting for the 10-minute cron.
    sync_note = ""
    try:
        sync_result = await email_sync.sync_account(session, account)
        await session.commit()
        sync_note = (
            f" First sync: {sync_result.fetched} message"
            f"{'s' if sync_result.fetched != 1 else ''} scanned, "
            f"{sync_result.new} new."
        )
    except Exception as exc:  # noqa: BLE001 — connect succeeded; sync is best-effort here
        log.warning("gmail first sync failed for account %s: %s", account.id, exc)
        sync_note = " First sync will run on the next 10-minute tick."

    response = HTMLResponse(
        '<div class="text-sm text-emerald-300">'
        f"Connected {account.account_email} — inbox tracking is live.{sync_note}"
        "</div>"
    )
    response.headers["HX-Trigger"] = _json.dumps(
        {
            "emailConnected": True,
            "showToast": {
                "tone": "success",
                "text": f"Gmail connected — {account.account_email}.{sync_note}",
            },
        }
    )
    return response


@router.post(
    "/api/v1/integrations/email/{account_id}/test",
    name="api_email_account_test",
)
async def test_account(
    account_id: int,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
) -> TestConnectionResult:
    user_id = _effective_user_id(_user)
    account = (
        await session.exec(
            select(EmailAccount).where(
                EmailAccount.id == account_id,
                EmailAccount.user_id == user_id,
                EmailAccount.deleted_at.is_(None),
            )
        )
    ).one_or_none()
    if account is None:
        raise HTTPException(status_code=404, detail="Email account not found")
    password = email_credentials.load_imap_password(account)
    if password is None:
        return TestConnectionResult(
            ok=False, error="credential decrypt failed; re-paste app-password"
        )
    ok, err = await email_sync.test_imap_connection(
        host=account.imap_host,
        port=account.imap_port,
        username=account.imap_username,
        password=password,
    )
    return TestConnectionResult(ok=ok, error=err)


@router.delete(
    "/api/v1/integrations/email/{account_id}",
    name="api_email_account_delete",
)
async def delete_account(
    account_id: int,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
) -> HTMLResponse:
    """Disconnect (soft-delete) an email account.

    Item 8 (2026-07): this used to return 204 — and htmx does NOT swap
    204 responses, so the card stayed on screen and Disconnect looked like
    it "did nothing" even though the row was soft-deleted. 200 + empty body
    swaps the card away (hx-swap="outerHTML" on `closest article`), and the
    toast says what happened.
    """
    import json as _json

    user_id = _effective_user_id(_user)
    account = (
        await session.exec(
            select(EmailAccount).where(
                EmailAccount.id == account_id,
                EmailAccount.user_id == user_id,
                EmailAccount.deleted_at.is_(None),
            )
        )
    ).one_or_none()
    if account is None:
        raise HTTPException(status_code=404, detail="Email account not found")
    account.deleted_at = datetime.now(UTC)
    account.updated_at = datetime.now(UTC)
    session.add(account)
    await session.commit()
    response = HTMLResponse("")
    response.headers["HX-Trigger"] = _json.dumps(
        {
            "showToast": {
                "tone": "success",
                "text": f"Disconnected {account.account_email} — inbox syncing stopped.",
            }
        }
    )
    return response


@router.post(
    "/api/v1/integrations/email/{account_id}/sync-now",
    name="api_email_account_sync_now",
)
async def sync_account_now(
    account_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
    _rl: None = Depends(check_email_sync_now_rate_limit),
):
    user_id = _effective_user_id(_user)
    account = (
        await session.exec(
            select(EmailAccount).where(
                EmailAccount.id == account_id,
                EmailAccount.user_id == user_id,
                EmailAccount.deleted_at.is_(None),
            )
        )
    ).one_or_none()
    if account is None:
        raise HTTPException(status_code=404, detail="Email account not found")
    result = await email_sync.sync_account(session, account)
    await session.commit()
    payload = {
        "account_id": result.account_id,
        "fetched": result.fetched,
        "new": result.new,
        "status": result.status.value,
        "errors": result.errors[:5],
    }
    # HTMX callers use hx-swap="none" — a JSON body renders nothing, so the
    # "Sync now" button was completely silent (item 3+4). Toast the summary.
    if request.headers.get("hx-request") == "true":
        import json as _json

        tone = "success" if result.status.value == "ok" else "warning"
        text = (
            f"Synced {account.account_email}: {result.fetched} scanned, {result.new} new."
            if tone == "success"
            else f"Sync hit trouble ({result.status.value}) — {'; '.join(result.errors[:1]) or 'check credentials'}."
        )
        response = HTMLResponse("")
        response.headers["HX-Trigger"] = _json.dumps({"showToast": {"tone": tone, "text": text}})
        return response
    return payload
