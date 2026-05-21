"""Generic LLM-driven ATS adapter — SKELETON (COMPANY_DIRECT fallback).

Per plan 63 / 0.2.7.10 § C.7 + D.7. The real adapter calls
`llm_tracker.tracked_call(prompt_name="ats_generic_form_fill",
schema=GenericFormFillPlan)` to translate page DOM into a sequence of
`(selector, value)` form-fill steps; below the
`ats_generic_llm_confidence_threshold` (default 0.7) → fail-fast as
`field_mismatch`. Hostile-template-injection mitigation lives in the prompt
template (Pydantic `extra="forbid"` + bounded string lengths + USER-CONTENT
fencing).

Implementation + hacker PLAN_GATE land in ROADMAP row 0.8.0.NN.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from models import Application, Job

from ._playwright_base import _PlaywrightATSAdapter
from .base import FAILURE_AUTH_REQUIRED, ApplicationBundle, SubmissionResult

if TYPE_CHECKING:
    from playwright.async_api import Page


class GenericAdapter(_PlaywrightATSAdapter):
    board_name = "company_direct"

    def can_submit(self, job: Job) -> bool:  # type: ignore[override]
        return False

    async def submit(  # type: ignore[override]
        self, application: Application, bundle: ApplicationBundle
    ) -> SubmissionResult:
        return SubmissionResult(
            ok=False,
            error=FAILURE_AUTH_REQUIRED,
            error_message=(
                "Generic ATS adapter ships in Phase 5 (ROADMAP row 0.8.0.NN). "
                "Uses LLM-driven form-fill with fail-fast fallback. "
                "Open the company link manually for now."
            ),
        )

    async def _submit_with_context(
        self, page: Page, application: Application, bundle: ApplicationBundle
    ) -> SubmissionResult:
        raise NotImplementedError(
            "GenericAdapter._submit_with_context lands in ROADMAP row 0.8.0.NN"
        )


__all__ = ["GenericAdapter"]
