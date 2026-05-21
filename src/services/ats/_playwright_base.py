"""Mixin base for Playwright-driven ATS adapters.

Per plan 63 / 0.2.7.10 § C.4. Owns the shared submission shell:
- Acquire a BrowserContext from the pool (board-specific UA)
- Top-level try/except wraps `_submit_with_context` with a best-effort
  screenshot capture; emit `raw["screenshot_b64"]` for postmortem
- Checkpoint persistence helper (`_checkpoint`) for multi-page submission
  flows (Workday is 5-7 pages; resume on transient failure within session)

Subclasses implement `_submit_with_context(page, application, bundle)`.
Skeleton adapters (this PR) bypass the mixin's `submit()` flow entirely and
return `FAILURE_AUTH_REQUIRED` directly — see § C.7 of the plan.
"""

from __future__ import annotations

import base64
import logging
from abc import abstractmethod
from typing import TYPE_CHECKING, Any

from models import Application

from ._browser_pool import ATSBrowserPool
from .base import (
    FAILURE_AUTH_REQUIRED,
    FAILURE_UNKNOWN,
    ApplicationBundle,
    ATSAdapter,
    SubmissionResult,
)

if TYPE_CHECKING:
    from playwright.async_api import Page

log = logging.getLogger(__name__)


class _PlaywrightATSAdapter(ATSAdapter):
    """Shared mixin for Playwright-driven adapters (Workday / LinkedIn / Indeed / Generic).

    `requires_browser_pool=True` signals to the dispatcher factory that the
    adapter needs a pool injected. Until the per-adapter PR wires the pool
    factory (0.4.0.NN), instances constructed without a pool return
    `FAILURE_AUTH_REQUIRED` — consistent with the existing `_ManualFallbackAdapter`
    envelope.
    """

    requires_browser_pool: bool = True
    board_name: str = "abstract"

    def __init__(self, *, browser_pool: ATSBrowserPool | None = None) -> None:
        self._pool = browser_pool

    def requires_credential(self) -> bool:
        return True

    async def submit(self, application: Application, bundle: ApplicationBundle) -> SubmissionResult:
        if self._pool is None:
            return SubmissionResult(
                ok=False,
                error=FAILURE_AUTH_REQUIRED,
                error_message=f"{self.board_name} adapter has no browser pool wired",
            )
        async with self._pool.acquire(board=self.board_name) as context:
            page = await context.new_page()
            try:
                return await self._submit_with_context(page, application, bundle)
            except Exception as exc:  # noqa: BLE001 — diagnostic capture
                screenshot_b64 = await self._safe_screenshot(page)
                return SubmissionResult(
                    ok=False,
                    error=FAILURE_UNKNOWN,
                    error_message=f"{self.board_name} adapter raised: {exc!r}",
                    raw={
                        "request_url": page.url,
                        "response_status": None,
                        "response_body": "<playwright-runtime-exception>",
                        "screenshot_b64": screenshot_b64,
                        "exception_type": type(exc).__name__,
                    },
                )

    @abstractmethod
    async def _submit_with_context(
        self, page: Page, application: Application, bundle: ApplicationBundle
    ) -> SubmissionResult:
        """Per-adapter submission flow (Workday's 5-7 pages, Easy Apply's 1-3, etc.)."""

    async def _safe_screenshot(self, page: Page) -> str | None:
        """Best-effort base64 PNG. Returns None on failure (page closed, etc.)."""
        try:
            png = await page.screenshot(full_page=True, type="png")
            return base64.b64encode(png).decode("ascii")
        except Exception as exc:  # noqa: BLE001 — diagnostic; never block
            log.debug("safe_screenshot suppressed: %s", exc)
            return None

    async def _checkpoint(
        self, application: Application, step_name: str, state: dict[str, Any]
    ) -> None:
        """Persist a mid-submission checkpoint to `submission_artifacts.<board>_checkpoint`.

        Per plan 63 § D.9 (Workday checkpoint). Skeleton stub here; the actual
        DB-write integration lands in the per-adapter PR (0.4.0.NN) where the
        adapter has an AsyncSession via the dispatcher factory.
        """
        return


__all__ = ["_PlaywrightATSAdapter"]
