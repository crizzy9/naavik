"""Tenant — stub multi-tenancy root (plan 62 / 0.2.7.07).

Single-row `id=1, name='self-hosted'` on self-host; future multi-tenancy
plan (0.8.0.NN) extends with billing + isolation columns. JWT signing keys
FK back to `Tenant.id` so per-tenant blast-radius isolation works the same
on self-host (one row) and cloud (N rows).

Per `docs/plans/62-0.2.7.07-jwt-rotation.md § B.1` + OQ.7.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel

from ._common import utcnow


class Tenant(SQLModel, table=True):
    __tablename__ = "tenant"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=128, unique=True, index=True)
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
