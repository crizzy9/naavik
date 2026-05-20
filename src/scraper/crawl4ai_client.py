"""Crawl4AIClient — testable wrapper around `AsyncWebCrawler`.

Per docs/design/SCRAPER_BASE.md § E + § G (plan 29 § D.4 Option B + plan 38).
Scrapers depend on this class (not Crawl4AI directly) so Crawl4AI upgrades
land in one place and tests can inject fakes. Matches
`src/llm/anthropic.py:AnthropicProvider` wrap-the-SDK convention.

`enable_stealth=True` is the default — first-line defense against Cloudflare /
WAF challenges. `UndetectedAdapter` engagement is per-source via the
`use_undetected_adapter` constructor flag (`ScraperBase` class attr threaded
through by the scheduler); engagement deferred per plan 38 § D.4.

Rate limiting (plan 38 § D.2):
- Per-process min-interval floor (jitter included) fires before every
  `arun` in `fetch_html` — necessary because Crawl4AI's `arun()` does NOT
  accept a `rate_limiter=` kwarg in 0.8.6 (only `MemoryAdaptiveDispatcher`
  accepts it).
- `MemoryAdaptiveDispatcher(rate_limiter=...)` fires in `stream_many` —
  this is Crawl4AI's native exponential-backoff path on 429 / 503, plus
  the per-batch token bucket.
- The min-interval floor still wins for sub-1-rpm sources (LinkedIn = 0.4
  rpm → 150s/request) where Crawl4AI's `base_delay` jitter would be too
  small to dominate.

Telemetry (plan 38 § D.7): instance counters `rate_limit_hits` +
`backoff_total_s` + `_ua` are read by `scraper_service.run_scraper` after
the stream completes and written into `JobScrapeRun.raw_meta`.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import AsyncIterator

from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CacheMode,
    CrawlerRunConfig,
    MemoryAdaptiveDispatcher,
    RateLimiter,
)
from pydantic import HttpUrl, TypeAdapter, ValidationError

from scraper.redaction import safe_exc, safe_msg, safe_url
from scraper.url_guard import is_safe_destination
from scraper.user_agents import pick_user_agent

log = logging.getLogger(__name__)

_HTTP_URL_ADAPTER: TypeAdapter[HttpUrl] = TypeAdapter(HttpUrl)

# Status codes Crawl4AI's RateLimiter retries on; matches the public docs
# default. 429 = Too Many Requests; 503 = Service Unavailable (transient).
_RATE_LIMIT_STATUS_CODES = (429, 503)


def _looks_rate_limited(result_status_code: int | None, result_error: str | None) -> bool:
    """Heuristic: did this CrawlResult fail because of a 429 / 503?

    Crawl4AI's `CrawlResult.status_code` is the upstream HTTP status when
    available; `error_message` is a free-form string. We check both because
    not every Crawl4AI failure-path populates `status_code` (timeout, DNS
    resolution failure, etc. only have `error_message`).
    """
    if result_status_code in _RATE_LIMIT_STATUS_CODES:
        return True
    if result_error is None:
        return False
    err = result_error.lower()
    return any(token in err for token in ("429", "503", "rate limit", "too many requests"))


class Crawl4AIClient:
    """Testable wrapper around Crawl4AI's `AsyncWebCrawler`.

    Two public methods cover the scraping shapes we use today:
    `fetch_html(url)` for one-shot single-URL fetches (used by detail-page
    scrapers), and `stream_many(urls)` for concurrent multi-URL fetches that
    yield (url, html) tuples as each result lands (used by listing-page
    expansion in site scrapers).

    Per plan 38 § D.2 adopt `crawl4ai.RateLimiter` for the multi-URL path's
    dispatcher; per plan 38 § D.8 `rate_limit_per_minute` is `float` so
    sub-1-rpm sources (LinkedIn 0.4) don't get floored.
    """

    def __init__(
        self,
        *,
        enable_stealth: bool = True,
        headless: bool = True,
        page_timeout_ms: int = 30_000,
        rate_limit_per_minute: float = 30.0,
        random_delay_seconds: tuple[float, float] = (1.0, 3.0),
        user_agent: str | None = None,
        use_undetected_adapter: bool = False,
    ) -> None:
        self._ua: str = user_agent or pick_user_agent()
        self._browser_config = BrowserConfig(
            enable_stealth=enable_stealth,
            headless=headless,
            user_agent=self._ua,
        )
        self._run_config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            page_timeout=page_timeout_ms,
        )
        self._rate_limit_per_minute = rate_limit_per_minute
        self._random_delay_seconds = random_delay_seconds
        # Min-interval floor (plan 38 § D.2): 60/rpm seconds between any two
        # requests within the same Crawl4AIClient instance. `max(0.1, ...)`
        # caps the floor at 600s (rpm=0.1) so a misconfigured Settings entry
        # can't deadlock the cron.
        self._min_interval_s = 60.0 / max(0.1, rate_limit_per_minute)
        self._last_request_at: float = 0.0

        # Crawl4AI RateLimiter (plan 38 § D.2): adds exponential backoff on
        # 429 / 503 to the multi-URL dispatcher. max_retries=2 + max_delay=60s
        # caps worst-case URL time at base + 2 * 60s (see risk table).
        self._rate_limiter = RateLimiter(
            base_delay=random_delay_seconds,
            max_delay=60.0,
            max_retries=2,
            rate_limit_codes=list(_RATE_LIMIT_STATUS_CODES),
        )

        # UndetectedAdapter engagement (plan 38 § D.4). Off by default;
        # subclass class-attr flips on per source if 403-rate justifies.
        self._use_undetected_adapter = use_undetected_adapter

        # Telemetry counters (plan 38 § D.7). Read by scraper_service after
        # the stream completes; written into JobScrapeRun.raw_meta.
        self.rate_limit_hits: int = 0
        self.backoff_total_s: float = 0.0

    @property
    def user_agent(self) -> str:
        """The UA string this instance pinned at construction time."""
        return self._ua

    def _make_crawler(self) -> AsyncWebCrawler:
        """Construct the `AsyncWebCrawler`; route via `UndetectedAdapter` when on.

        Crawl4AI 0.8.6 wires `UndetectedAdapter` via
        `crawler_strategy=AsyncPlaywrightCrawlerStrategy(browser_adapter=...)`.
        `AsyncPlaywrightCrawlerStrategy` lives in
        `crawl4ai.async_crawler_strategy`, not the package root. Lazy-import
        inside the branch so the substrate doesn't pay the cost when the
        flag is off.
        """
        if self._use_undetected_adapter:
            from crawl4ai import UndetectedAdapter
            from crawl4ai.async_crawler_strategy import AsyncPlaywrightCrawlerStrategy

            return AsyncWebCrawler(
                crawler_strategy=AsyncPlaywrightCrawlerStrategy(
                    browser_config=self._browser_config,
                    browser_adapter=UndetectedAdapter(),
                ),
            )
        return AsyncWebCrawler(config=self._browser_config)

    async def fetch_html(self, url: str) -> str | None:
        """Fetch one URL; return HTML on success, `None` on a non-fatal failure.

        URL validates through `pydantic.HttpUrl`; non-http(s) schemes
        (file/ftp/gopher/data/javascript) return None without invoking Crawl4AI.
        Crawl4AI errors propagate via `result.success=False`; we log + return
        `None` so scraper subclasses can append to `self._errors` and continue.
        429 / 503 failures bump `rate_limit_hits` so operator telemetry can
        surface throttling.
        """
        try:
            validated = _HTTP_URL_ADAPTER.validate_python(url)
        except ValidationError as exc:
            log.warning(
                "crawl4ai fetch rejected: url=%s reason=%s",
                safe_url(url),
                safe_exc(exc),
            )
            return None
        safe, reason = is_safe_destination(str(validated))
        if not safe:
            log.warning(
                "crawl4ai fetch url-guard blocked: url=%s reason=%s",
                safe_url(url),
                reason,
            )
            return None
        await self._enforce_min_interval()
        async with self._make_crawler() as crawler:
            result = await crawler.arun(url=str(validated), config=self._run_config)
        if not result.success:
            status_code = getattr(result, "status_code", None)
            error_msg = getattr(result, "error_message", None)
            if _looks_rate_limited(status_code, error_msg):
                self.rate_limit_hits += 1
            log.warning(
                "crawl4ai fetch failed: url=%s err=%s",
                safe_url(url),
                safe_msg(error_msg),
            )
            return None
        return result.html

    async def stream_many(
        self,
        urls: list[str],
    ) -> AsyncIterator[tuple[str, str | None]]:
        """Fetch many URLs concurrently; yield `(url, html|None)` per result.

        Uses Crawl4AI's native streaming dispatcher with `rate_limiter` wired
        in (plan 38 § D.2). `max_session_permit` is sized off
        `rate_limit_per_minute` so a 30/min cap maps to ~5 concurrent
        sessions — gentle enough that bursting doesn't break the cap.
        """
        validated: list[str] = []
        for raw in urls:
            try:
                checked = str(_HTTP_URL_ADAPTER.validate_python(raw))
            except ValidationError as exc:
                log.warning(
                    "crawl4ai stream-many rejected: url=%s reason=%s",
                    safe_url(raw),
                    safe_exc(exc),
                )
                continue
            safe, reason = is_safe_destination(checked)
            if not safe:
                log.warning(
                    "crawl4ai stream-many url-guard blocked: url=%s reason=%s",
                    safe_url(raw),
                    reason,
                )
                continue
            validated.append(checked)
        if not validated:
            return
        streaming_config = self._run_config.clone(stream=True)
        dispatcher = MemoryAdaptiveDispatcher(
            memory_threshold_percent=85.0,
            max_session_permit=max(1, int(self._rate_limit_per_minute) // 6 or 1),
            rate_limiter=self._rate_limiter,
        )

        batch_started_at = time.monotonic()
        async with self._make_crawler() as crawler:
            async for result in await crawler.arun_many(
                urls=validated,
                config=streaming_config,
                dispatcher=dispatcher,
            ):
                if result.success:
                    yield (result.url, result.html)
                else:
                    status_code = getattr(result, "status_code", None)
                    error_msg = getattr(result, "error_message", None)
                    if _looks_rate_limited(status_code, error_msg):
                        self.rate_limit_hits += 1
                    log.warning(
                        "crawl4ai stream-result failed: url=%s err=%s",
                        safe_url(result.url),
                        safe_msg(error_msg),
                    )
                    yield (result.url, None)
        # Best-effort backoff accumulator. Crawl4AI's RateLimiter does not
        # surface its internal sleep totals; using wall-clock duration as an
        # upper bound makes the telemetry surface non-zero when retries fire.
        self.backoff_total_s += time.monotonic() - batch_started_at

    async def _enforce_min_interval(self) -> None:
        """Sleep so requests/minute stays under the cap; add jitter."""
        now = asyncio.get_running_loop().time()
        elapsed = now - self._last_request_at
        if elapsed < self._min_interval_s:
            await asyncio.sleep(self._min_interval_s - elapsed)
        jitter = random.uniform(*self._random_delay_seconds)
        await asyncio.sleep(jitter)
        self._last_request_at = asyncio.get_running_loop().time()
