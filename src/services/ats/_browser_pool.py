"""Shared Playwright Browser + per-submission BrowserContext pool.

Per plan 63 / 0.2.7.10 § C.3 (locked decision D.2). One `Browser` per process
amortized across all `submit()` calls; one `BrowserContext` per `acquire()`
for state isolation (fresh cookies / storage / fingerprint). Hard cap on
concurrent contexts via `asyncio.Semaphore` (default 4 — Workday/LinkedIn
each spawn full Chromium tabs so RAM is the bottleneck).

Lifecycle:
- `start()` boots a Browser **once per process** (idempotent; lazy — first
  `acquire()` triggers it so FastAPI lifespan init pays zero Chromium-launch
  latency).
- `acquire(board)` yields a fresh BrowserContext with board-specific UA
  (rotated from `scraper.user_agents.pick_user_agent`) + 1440x900 viewport.
- `stop()` closes Browser + Playwright on shutdown.

Production wiring (per-adapter PR 0.4.0.NN / 0.8.0.NN): the FastAPI lifespan
constructs one `ATSBrowserPool` and parks it on `app.state.ats_browser_pool`.
Each adapter pulls the pool from the bundle's `playwright_browser_factory`
hook or via the dispatch factory (sketched in `_playwright_base.py`).
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from playwright.async_api import Browser, BrowserContext

log = logging.getLogger(__name__)

_DEFAULT_MAX_CONTEXTS = 4
_DEFAULT_VIEWPORT = {"width": 1440, "height": 900}


class ATSBrowserPool:
    """Shared Playwright Browser instance + per-submission BrowserContext pool.

    Subclasses must not override `acquire`. Override `_inject_session_cookies`
    when a board needs board-specific cookie hydration.
    """

    def __init__(
        self,
        *,
        max_concurrent_contexts: int = _DEFAULT_MAX_CONTEXTS,
        headless: bool = True,
        browser_type: str = "chromium",
    ) -> None:
        if max_concurrent_contexts < 1:
            raise ValueError("max_concurrent_contexts must be >= 1")
        self._sem = asyncio.Semaphore(max_concurrent_contexts)
        self._headless = headless
        self._browser_type = browser_type
        self._playwright = None
        self._browser: Browser | None = None
        self._started = False
        self._start_lock = asyncio.Lock()

    @property
    def started(self) -> bool:
        return self._started

    @property
    def max_concurrent_contexts(self) -> int:
        return self._sem._value + len(getattr(self._sem, "_waiters", None) or ())  # type: ignore[attr-defined]

    async def start(self) -> None:
        """Boot Playwright + Browser. Idempotent + safe under concurrent first-calls."""
        if self._started:
            return
        async with self._start_lock:
            if self._started:
                return
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            launch_fn = getattr(self._playwright, self._browser_type).launch
            self._browser = await launch_fn(headless=self._headless)
            self._started = True
            log.info(
                "ATSBrowserPool started: %s headless=%s max_contexts=%d",
                self._browser_type,
                self._headless,
                self._sem._value,  # type: ignore[attr-defined]
            )

    async def stop(self) -> None:
        """Tear down Browser + Playwright. Safe to call multiple times."""
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception as exc:  # noqa: BLE001 — shutdown is best-effort
                log.warning("ATSBrowserPool browser close failed: %s", exc)
            self._browser = None
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception as exc:  # noqa: BLE001 — shutdown is best-effort
                log.warning("ATSBrowserPool playwright stop failed: %s", exc)
            self._playwright = None
        self._started = False

    @asynccontextmanager
    async def acquire(
        self, *, board: str, user_agent: str | None = None
    ) -> AsyncIterator[BrowserContext]:
        """Yield a fresh BrowserContext bounded by the concurrency Semaphore.

        Context is closed on exit; cookies / storage / fingerprint never bleed
        across `acquire()` calls. Per-board UA picked from the rotated pool;
        caller may override via `user_agent=...`.
        """
        if not self._started:
            await self.start()
        assert self._browser is not None  # set by start()
        if user_agent is None:
            from scraper.user_agents import pick_user_agent

            ua = pick_user_agent()
        else:
            ua = user_agent
        async with self._sem:
            context = await self._browser.new_context(
                user_agent=ua,
                viewport=_DEFAULT_VIEWPORT,
            )
            try:
                await self._inject_session_cookies(context, board)
                yield context
            finally:
                try:
                    await context.close()
                except Exception as exc:  # noqa: BLE001 — context teardown best-effort
                    log.warning("ATSBrowserPool context close failed: %s", exc)

    async def _inject_session_cookies(self, context: BrowserContext, board: str) -> None:
        """Hook for per-adapter session-cookie injection.

        Default: no-op. The skeleton adapters override in their per-adapter PR
        (0.4.0.NN / 0.8.0.NN) — Workday reads `WORKDAY_LOGIN_TOKEN`, LinkedIn
        reads `LINKEDIN_SESSION_COOKIE`, etc. When env slot is unset, the
        adapter's `submit()` path predictably returns `FAILURE_AUTH_REQUIRED`
        without ever needing a cookie.
        """
        return


__all__ = ["ATSBrowserPool"]
