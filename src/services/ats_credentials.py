"""ATS credential metadata service — Wave 4 of plan 10 § B.6.

DB-side `ATSCredential` row carries metadata only (`has_credential`,
`login_status`, `last_login_at`, `last_failure_kind`). Plan 26 (0.2.0.01)
deleted the encrypted vault that previously held cookie / token blobs;
Phase 2.X adapter plans (Workday / LinkedIn / Indeed) re-introduce a
DB-side storage model when actually needed. Until then this module only
serves UI-facing metadata.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import ApplicationBoard, ATSCredential, AtsLoginStatus


async def get_credential_metadata(
    session: AsyncSession,
    user_id: int,
    board: ApplicationBoard,
) -> ATSCredential | None:
    stmt = select(ATSCredential).where(
        ATSCredential.user_id == user_id,
        ATSCredential.board == board,
    )
    return (await session.exec(stmt)).one_or_none()


async def list_credential_metadata(
    session: AsyncSession,
    user_id: int,
) -> list[ATSCredential]:
    stmt = select(ATSCredential).where(ATSCredential.user_id == user_id)
    return (await session.exec(stmt)).all()


async def upsert_credential_metadata(
    session: AsyncSession,
    user_id: int,
    board: ApplicationBoard,
    *,
    has_credential: bool | None = None,
    login_status: AtsLoginStatus | None = None,
    last_login_at: datetime | None = None,
    last_failure_kind: str | None = None,
) -> ATSCredential:
    row = await get_credential_metadata(session, user_id, board)
    now = datetime.now(UTC)
    if row is None:
        row = ATSCredential(
            user_id=user_id,
            board=board,
            has_credential=has_credential if has_credential is not None else False,
            login_status=login_status or AtsLoginStatus.NOT_CONFIGURED,
            last_login_at=last_login_at,
            last_failure_kind=last_failure_kind,
            created_at=now,
            updated_at=now,
        )
    else:
        if has_credential is not None:
            row.has_credential = has_credential
        if login_status is not None:
            row.login_status = login_status
        if last_login_at is not None:
            row.last_login_at = last_login_at
        if last_failure_kind is not None:
            row.last_failure_kind = last_failure_kind
        row.updated_at = now
    session.add(row)
    await session.flush()
    return row
