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

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from api.auth import require_csrf
from db.session import get_session
from models import EmailAccount, EmailAccountStatus, User
from models.enums import EmailAccountProvider
from services import email_credentials, email_sync
from services.auth import require_authed_session
from ui.routes.profile import _effective_user_id

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


@router.post("/api/v1/integrations/email/imap", name="api_email_account_connect")
async def connect_imap(
    account_email: Annotated[EmailStr, Form()],
    imap_host: Annotated[str, Form()],
    imap_username: Annotated[str, Form()],
    imap_password: Annotated[str, Form()],
    imap_port: Annotated[int, Form()] = 993,
    imap_use_tls: Annotated[bool, Form()] = True,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
) -> EmailAccountRead:
    user_id = _effective_user_id(_user)

    ok, err = await email_sync.test_imap_connection(
        host=imap_host,
        port=imap_port,
        username=imap_username,
        password=imap_password,
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"IMAP connection failed: {err or 'unknown'}",
        )

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
        await session.commit()
        return EmailAccountRead.model_validate(existing)

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
    await session.commit()
    return EmailAccountRead.model_validate(account)


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
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_account(
    account_id: int,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
) -> None:
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


@router.post(
    "/api/v1/integrations/email/{account_id}/sync-now",
    name="api_email_account_sync_now",
)
async def sync_account_now(
    account_id: int,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
) -> dict[str, object]:
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
    return {
        "account_id": result.account_id,
        "fetched": result.fetched,
        "new": result.new,
        "status": result.status.value,
        "errors": result.errors[:5],
    }
