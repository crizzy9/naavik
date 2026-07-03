"""Workday ATS adapter — SKELETON.

Per plan 63 / 0.2.7.10 § C.7. Skeleton intentionally returns
`FAILURE_AUTH_REQUIRED` rather than raising — UX-equivalent to the prior
`_ManualFallbackAdapter` envelope; the win is that the dispatcher now resolves
to a concrete board-named class so logs say `[workday] auth_required` instead
of `[fallback-workday] auth_required`, and the per-adapter PR is a 1-file
overwrite rather than a registry-edit + new-file triple-change.

Implementation lands in ROADMAP row 0.4.0.NN (sequenced post-Phase-3 scoring).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from models import Application, Job

from ._playwright_base import _PlaywrightATSAdapter
from .base import FAILURE_AUTH_REQUIRED, ApplicationBundle, SubmissionResult

if TYPE_CHECKING:
    from playwright.async_api import Page


class WorkdayAdapter(_PlaywrightATSAdapter):
    board_name = "workday"

    def can_submit(self, job: Job) -> bool:  # type: ignore[override]
        # Skeleton: never claims to submit. 0.4.0.NN flips this to URL pattern match.
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
                "Workday adapter ships in Phase 4 (ROADMAP row 0.4.0.NN). "
                "Open the ATS link manually for now; "
                "track progress at ROADMAP § Phase 4."
            ),
        )

    async def _submit_with_context(
        self, page: Page, application: Application, bundle: ApplicationBundle
    ) -> SubmissionResult:
        raise NotImplementedError(
            "WorkdayAdapter._submit_with_context lands in ROADMAP row 0.4.0.NN"
        )


__all__ = ["WorkdayAdapter"]
