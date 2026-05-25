"""User entity — identity + auth root.

Per DATA_MODEL.md § C `User`. password_hash is bcrypt cost=12 in production
(cost=4 in tests via `NAAVIK_BCRYPT_COST` env override). Never logged.

Wave 3 ships without SQLModel `Relationship()` declarations — services use
explicit `select(...).where(FK)` joins. Wave 6 may revisit once we move
fully to SQLAlchemy 2.0 `Mapped[]` annotations.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel

from ._common import utcnow


class User(SQLModel, table=True):
    __tablename__ = "user"

    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True, max_length=320)
    password_hash: str = Field(max_length=256)

    is_active: bool = Field(default=True)
    # Plan 0.7.0.48 Wave 2 (2026-05-25): deprecated — every user has full
    # ownership of their own data. No admin-only operations exist in this app.
    # Column kept for schema compat; drop migration filed as 0.7.0.49 follow-up.
    is_admin: bool = Field(default=True)

    # Plan 18 (PC.6, 2026-05-17): forced-rotation flag. Cleared on the first
    # successful POST /api/v1/auth/change-password that satisfies
    # services.auth.validate_password_complexity. While True,
    # services.auth.require_password_complete redirects every authed request
    # to /auth/change-password. Plan 83 (0.7.0.36, 2026-05-21) retains the
    # column for future use; default stays False since no auto-seed flow
    # sets it anymore.
    must_change_password: bool = Field(default=False)

    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    last_login_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    deleted_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
