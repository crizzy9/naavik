"""Shared utility helpers for SQLModel entities."""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Default factory: timezone-aware UTC datetime."""
    return datetime.now(UTC)
