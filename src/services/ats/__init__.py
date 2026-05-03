"""ATS adapter dispatcher.

Per BACKEND.md § K.5 + plan 10 § C.4. Wave 6 ships Greenhouse / Lever / Ashby.
Workday / LinkedIn / Indeed / Generic are Phase 1.x sub-prompt — calls return
`SubmissionResult(ok=False, error="auth_required")` until those adapters land.
"""

from __future__ import annotations

from models import ApplicationBoard

from .base import (
    ALL_FAILURE_KINDS,
    FAILURE_AUTH_REQUIRED,
    FAILURE_CAPTCHA,
    FAILURE_FIELD_MISMATCH,
    FAILURE_RATE_LIMIT,
    FAILURE_UNKNOWN,
    ApplicationBundle,
    ATSAdapter,
    ATSError,
    SubmissionResult,
)


def dispatch(board: ApplicationBoard) -> ATSAdapter:
    """Return the adapter for `board`. Falls back to manual stub for unknown."""
    if board == ApplicationBoard.GREENHOUSE:
        from .greenhouse import GreenhouseAdapter

        return GreenhouseAdapter()
    if board == ApplicationBoard.LEVER:
        from .lever import LeverAdapter

        return LeverAdapter()
    if board == ApplicationBoard.ASHBY:
        from .ashby import AshbyAdapter

        return AshbyAdapter()
    # Workday / LinkedIn / Indeed / Generic / Manual / company_direct →
    # not yet implemented in Wave 6; auth_required stub.
    return _ManualFallbackAdapter(board)


class _ManualFallbackAdapter(ATSAdapter):
    """Fallback for boards we can't auto-submit yet."""

    def __init__(self, board: ApplicationBoard) -> None:
        self.board = board
        self.board_name = board.value

    async def submit(self, application, bundle):  # type: ignore[override]
        return SubmissionResult(
            ok=False,
            error=FAILURE_AUTH_REQUIRED,
            error_message=(
                f"{self.board.value} requires Phase 1.x adapter (Playwright + credentials);"
                " open the ATS link manually for now"
            ),
        )

    def can_submit(self, job) -> bool:  # type: ignore[override]
        return False

    def requires_credential(self) -> bool:  # type: ignore[override]
        return True


__all__ = [
    "ALL_FAILURE_KINDS",
    "ATSAdapter",
    "ATSError",
    "ApplicationBundle",
    "FAILURE_AUTH_REQUIRED",
    "FAILURE_CAPTCHA",
    "FAILURE_FIELD_MISMATCH",
    "FAILURE_RATE_LIMIT",
    "FAILURE_UNKNOWN",
    "SubmissionResult",
    "dispatch",
]
