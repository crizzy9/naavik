"""LinkedIn Easy Apply ATS adapter — SKELETON.

Per plan 63 / 0.2.7.10 § C.7 + D.4 (hybrid Easy Apply preferred + external
fallback). Skeleton returns `FAILURE_AUTH_REQUIRED`.

Implementation lands in ROADMAP row 0.8.0.NN — high LinkedIn ban risk;
mitigations in plan 63 § D.4 (default OFF, score >= 0.95 gate, <= 3/day
cadence cap, operator-visible disclosure).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from models import Application, Job

from ._playwright_base import _PlaywrightATSAdapter
from .base import FAILURE_AUTH_REQUIRED, ApplicationBundle, SubmissionResult

if TYPE_CHECKING:
    from playwright.async_api import Page


class LinkedInAdapter(_PlaywrightATSAdapter):
    board_name = "linkedin"

    def can_submit(self, job: Job) -> bool:  # type: ignore[override]
        return False

    async def submit(  # type: ignore[override]
        self, application: Application, bundle: ApplicationBundle
    ) -> SubmissionResult:
        return SubmissionResult(
            ok=False,
            error=FAILURE_AUTH_REQUIRED,
            error_message=(
                "LinkedIn Easy Apply adapter ships in Phase 5 (ROADMAP row 0.8.0.NN). "
                "Carries account-ban risk; default OFF when shipped. "
                "Open the LinkedIn job manually for now."
            ),
        )

    async def _submit_with_context(
        self, page: Page, application: Application, bundle: ApplicationBundle
    ) -> SubmissionResult:
        raise NotImplementedError(
            "LinkedInAdapter._submit_with_context lands in ROADMAP row 0.8.0.NN"
        )


__all__ = ["LinkedInAdapter"]
