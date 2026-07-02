"""RevokedJwt — server-side JWT denylist for defense-in-depth post-rotation.

Plan 50 (0.2.1.04, 2026-05-20). After a successful password change the
rotating user's current `jti` is inserted here; auth resolution checks
this table on every request. Rows are pruned by
`admin.cleanup_revoked_jwts` cron (daily 03:30 UTC) when `expires_at`
passes; lookups are O(1) via the unique index on `jti`.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel

from ._common import utcnow


class RevokedJwt(SQLModel, table=True):
    __tablename__ = "revoked_jwt"

    id: int | None = Field(default=None, primary_key=True)
    jti: str = Field(unique=True, index=True, max_length=64)
    user_id: int = Field(foreign_key="user.id", ondelete="CASCADE", index=True)
    revoked_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    expires_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )
