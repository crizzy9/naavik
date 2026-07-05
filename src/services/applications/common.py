"""Shared foundations for the applications package (plan 91 Phase 4.2).

Exceptions + the AppEvent emitter + the `svc()` facade accessor. Internal
cross-seam calls go through `svc()` — the `services.application_service`
facade — so the ~60 conftest attribute shims and the
`patch("services.application_service.X")` targets keep intercepting them
(plan 91 cross-cutting rule 1).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from models import AppEvent, AppEventKind


class ApplicationServiceError(Exception):
    """Generic service-layer failure."""


class ValidationError(ApplicationServiceError):
    """`validate_submittable` rejected the application."""

    def __init__(self, message: str, *, code: str = "validation_failed") -> None:
        super().__init__(message)
        self.code = code


class IllegalStateTransition(ApplicationServiceError):
    """Backwards / forbidden status transition."""


def svc():
    """The `services.application_service` facade, resolved at call time."""
    from services import application_service

    return application_service


async def _emit_event(
    session: AsyncSession,
    *,
    user_id: int,
    application_id: int | None,
    kind: AppEventKind,
    payload: dict[str, Any] | None = None,
    actor: str | None = None,
) -> AppEvent:
    ev = AppEvent(
        user_id=user_id,
        application_id=application_id,
        kind=kind,
        payload=payload or {},
        actor=actor,
        occurred_at=datetime.now(UTC),
    )
    session.add(ev)
    await session.flush()
    return ev
