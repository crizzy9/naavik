"""ApiUsage — per-LLM-call cost + token + latency log.

Per DATA_MODEL.md § C `ApiUsage` (entity #19, promoted to Phase 1 on 2026-05-01
because Settings · LLM Provider cost cards need it from day one).

Wrapped around every `LLMProvider.complete / structured / stream` call by
`services/llm_tracker.py` (BACKEND.md § M.4). Aggregated daily by the
`admin.aggregate_costs` cron.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Index, Numeric
from sqlmodel import Field, SQLModel

from ._common import utcnow
from .enums import LLMProvider


class ApiUsage(SQLModel, table=True):
    __tablename__ = "api_usage"
    __table_args__ = (
        Index("ix_api_usage_user_occurred", "user_id", "occurred_at"),
        Index(
            "ix_api_usage_user_provider_occurred",
            "user_id",
            "provider",
            "occurred_at",
        ),
        Index(
            "ix_api_usage_application",
            "application_id",
            postgresql_where="application_id IS NOT NULL",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", ondelete="CASCADE", index=True)
    application_id: int | None = Field(
        default=None,
        foreign_key="application.id",
        ondelete="SET NULL",
        index=True,
    )

    provider: LLMProvider
    model: str
    method: str  # "complete" | "structured" | "stream"
    prompt_name: str | None = None

    input_tokens: int
    output_tokens: int
    # Numeric(10,4) in Postgres (plan 91 7.2) — float columns accumulate
    # binary-representation error on money. asdecimal=False keeps Python
    # reads as float so no caller changes type.
    cost_usd: float = Field(sa_column=Column(Numeric(10, 4, asdecimal=False), nullable=False))
    latency_ms: int

    succeeded: bool = Field(default=True)
    error_kind: str | None = None

    occurred_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
