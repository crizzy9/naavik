"""AppEvent — unified timeline event.

Per DATA_MODEL.md § C, § M. payload is JSONB; per-kind shape lives in
`app_event_payloads.py` as a discriminated Pydantic union.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from ._common import utcnow
from .enums import AppEventKind


class AppEvent(SQLModel, table=True):
    __tablename__ = "app_event"
    __table_args__ = (
        Index("ix_app_event_app_occurred", "application_id", "occurred_at"),
        Index("ix_app_event_user_kind_occurred", "user_id", "kind", "occurred_at"),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    application_id: int | None = Field(
        default=None,
        foreign_key="application.id",
        index=True,
    )

    kind: AppEventKind
    occurred_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )
    payload: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
    )
    actor: str | None = None

    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

