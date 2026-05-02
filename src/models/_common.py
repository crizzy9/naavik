"""Shared column factories + utility helpers for SQLModel entities.

Centralized here so every entity's tz-aware timestamp, JSONB column, and
ARRAY column stay consistent.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB


def utcnow() -> datetime:
    """Default factory: timezone-aware UTC datetime."""
    return datetime.now(UTC)


def tz_datetime_column(*, nullable: bool = False, index: bool = False) -> Column:
    """Postgres `TIMESTAMP WITH TIME ZONE` column."""
    return Column(DateTime(timezone=True), nullable=nullable, index=index)


def array_text_column(*, nullable: bool = False) -> Column:
    """Postgres `TEXT[]` column (uses `String` to round-trip lists)."""
    return Column(ARRAY(String), nullable=nullable)


def jsonb_column(*, nullable: bool = True) -> Column:
    """Postgres `JSONB` column."""
    return Column(JSONB, nullable=nullable)
