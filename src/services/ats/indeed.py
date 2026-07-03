"""Indeed ATS adapter — SKELETON.

Per plan 63 / 0.2.7.10 § C.7. Skeleton returns `FAILURE_AUTH_REQUIRED`.
Implementation lands in ROADMAP row 0.8.0.NN.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from models import Application, Job

from ._playwright_base import _PlaywrightATSAdapter
from .base import FAILURE_AUTH_REQUIRED, ApplicationBundle, SubmissionResult

if TYPE_CHECKING:
    from playwright.async_api import Page


class IndeedAdapter(_PlaywrightATSAdapter):
    board_name = "indeed"

    def can_submit(self, job: Job) -> bool:  # type: ignore[override]
        return False

    async def submit(  # type: ignore[override]
        self,
        application: Application,
        bundle: ApplicationBundle,
        *,
        dry_run: bool = False,
    ) -> SubmissionResult:
        del dry_run  # honest hand-off boards never reach a submit click
        return SubmissionResult(
            ok=False,
            error=FAILURE_AUTH_REQUIRED,
            error_message=(
                "Indeed adapter ships in Phase 5 (ROADMAP row 0.8.0.NN). "
                "Open the Indeed job manually for now."
            ),
        )

    async def _submit_with_context(
        self, page: Page, application: Application, bundle: ApplicationBundle
    ) -> SubmissionResult:
        raise NotImplementedError(
            "IndeedAdapter._submit_with_context lands in ROADMAP row 0.8.0.NN"
        )


__all__ = ["IndeedAdapter"]
