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
    is_admin: bool = Field(default=False)

    # Plan 18 (PC.6, 2026-05-17): set True at seed time when the dev password
    # is server-generated (no NAAVIK_DEV_PASSWORD override). Cleared on the
    # first successful POST /api/v1/auth/change-password that satisfies
    # services.auth.validate_password_complexity. While True,
    # services.auth.require_password_complete redirects every authed request
    # to /auth/change-password.
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
