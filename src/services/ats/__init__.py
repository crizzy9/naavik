"""ATS adapter dispatcher.

Per BACKEND.md § K.5 + plan 10 § C.4 + plan 63 / 0.2.7.10 § C.7. Wave 6
shipped Greenhouse / Lever / Ashby (HTTP-API adapters). Plan 63 added skeleton
modules for Workday / LinkedIn / Indeed / Generic (COMPANY_DIRECT) — they
return `FAILURE_AUTH_REQUIRED` envelopes with board-named log lines until
each per-adapter PR lands (Workday → 0.4.0.NN; the other three → 0.8.0.NN).
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

# Boards with a REAL auto-submit path today. Workday / LinkedIn / Indeed /
# Generic modules exist but return FAILURE_AUTH_REQUIRED stubs until their
# per-adapter PRs land — queueing those boards for auto-apply would sit
# forever, so the queue processor routes them to READY_TO_SUBMIT instead.
SUPPORTED_AUTO_SUBMIT_BOARDS: frozenset[ApplicationBoard] = frozenset(
    {
        ApplicationBoard.GREENHOUSE,
        ApplicationBoard.LEVER,
        ApplicationBoard.ASHBY,
    }
)


def board_supports_auto_submit(board: ApplicationBoard | None) -> bool:
    """True when `board` has a working end-to-end submit adapter."""
    return board is not None and board in SUPPORTED_AUTO_SUBMIT_BOARDS


def dispatch(board: ApplicationBoard) -> ATSAdapter:
    """Return the adapter for `board`. Falls back to manual stub for MANUAL."""
    if board == ApplicationBoard.GREENHOUSE:
        from .greenhouse import GreenhouseAdapter

        return GreenhouseAdapter()
    if board == ApplicationBoard.LEVER:
        from .lever import LeverAdapter

        return LeverAdapter()
    if board == ApplicationBoard.ASHBY:
        from .ashby import AshbyAdapter

        return AshbyAdapter()
    if board == ApplicationBoard.WORKDAY:
        from .workday import WorkdayAdapter

        return WorkdayAdapter()
    if board == ApplicationBoard.LINKEDIN:
        from .linkedin_apply import LinkedInAdapter

        return LinkedInAdapter()
    if board == ApplicationBoard.INDEED:
        from .indeed import IndeedAdapter

        return IndeedAdapter()
    if board == ApplicationBoard.COMPANY_DIRECT:
        from .generic import GenericAdapter

        return GenericAdapter()
    # ApplicationBoard.MANUAL → no auto-submission ever.
    return _ManualFallbackAdapter(board)


class _ManualFallbackAdapter(ATSAdapter):
    """Fallback for boards we can't auto-submit yet."""

    def __init__(self, board: ApplicationBoard) -> None:
        self.board = board
        self.board_name = board.value

    async def submit(self, application, bundle, *, dry_run: bool = False):  # type: ignore[override]
        del dry_run
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
    "SUPPORTED_AUTO_SUBMIT_BOARDS",
    "ATSAdapter",
    "ATSError",
    "ApplicationBundle",
    "board_supports_auto_submit",
    "FAILURE_AUTH_REQUIRED",
    "FAILURE_CAPTCHA",
    "FAILURE_FIELD_MISMATCH",
    "FAILURE_RATE_LIMIT",
    "FAILURE_UNKNOWN",
    "SubmissionResult",
    "dispatch",
]
