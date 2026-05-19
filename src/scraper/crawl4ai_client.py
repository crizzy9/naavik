"""Crawl4AIClient — testable wrapper around `AsyncWebCrawler`.

Per docs/design/SCRAPER_BASE.md § E (plan 29 § D.4 Option B). Scrapers depend
on this class (not Crawl4AI directly) so Crawl4AI upgrades land in one place
and tests can inject fakes. Matches `src/llm/anthropic.py:AnthropicProvider`
wrap-the-SDK convention.

`enable_stealth=True` is the default — first-line defense against Cloudflare /
WAF challenges per docs/design/research/LINKEDIN_SCRAPING.md § 6 risk #3.
`UndetectedAdapter` engagement is deferred to 0.2.0.13.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import AsyncIterator

from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CacheMode,
    CrawlerRunConfig,
    MemoryAdaptiveDispatcher,
)
from pydantic import HttpUrl, TypeAdapter, ValidationError

from scraper.redaction import safe_exc, safe_url

log = logging.getLogger(__name__)

# Module-level adapter; pydantic.HttpUrl rejects non-http(s) schemes
# (file/ftp/gopher/data/javascript) — SSRF/LFI block per plan 31 D.1.
_HTTP_URL_ADAPTER: TypeAdapter[HttpUrl] = TypeAdapter(HttpUrl)


class Crawl4AIClient:
    """Testable wrapper around Crawl4AI's `AsyncWebCrawler`.

    Two public methods cover the scraping shapes we use today:
    `fetch_html(url)` for one-shot single-URL fetches (used by detail-page
    scrapers), and `stream_many(urls)` for concurrent multi-URL fetches that
    yield (url, html) tuples as each result lands (used by listing-page
    expansion in site scrapers).

    The rate-limiter is intentionally simple — per-process token-bucket with
    `random_delay_seconds` jitter. Source-specific tuning (LinkedIn <=24/hr,
    etc.) lands in 0.2.0.13.
    """

    def __init__(
        self,
        *,
        enable_stealth: bool = True,
        headless: bool = True,
        page_timeout_ms: int = 30_000,
        rate_limit_per_minute: int = 30,
        random_delay_seconds: tuple[float, float] = (1.0, 3.0),
    ) -> None:
        self._browser_config = BrowserConfig(
            enable_stealth=enable_stealth,
            headless=headless,
        )
        self._run_config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            page_timeout=page_timeout_ms,
        )
        self._rate_limit_per_minute = rate_limit_per_minute
        self._random_delay_seconds = random_delay_seconds
        self._last_request_at: float = 0.0

    async def fetch_html(self, url: str) -> str | None:
        """Fetch one URL; return HTML on success, `None` on a non-fatal failure.

        URL validates through `pydantic.HttpUrl`; non-http(s) schemes
        (file/ftp/gopher/data/javascript) return None without invoking Crawl4AI.
        Crawl4AI errors propagate via `result.success=False`; we log + return
        `None` so scraper subclasses can append to `self._errors` and continue.
        Truly fatal errors (network down, auth invalid) raise — caller's
        responsibility to catch + mark `JobScrapeRun.status=FAILED`.
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
        await self._respect_rate_limit()
        async with AsyncWebCrawler(config=self._browser_config) as crawler:
            result = await crawler.arun(url=str(validated), config=self._run_config)
        if not result.success:
            log.warning(
                "crawl4ai fetch failed: url=%s err=%s",
                safe_url(url),
                result.error_message,
            )
            return None
        return result.html

    async def stream_many(
        self,
        urls: list[str],
    ) -> AsyncIterator[tuple[str, str | None]]:
        """Fetch many URLs concurrently; yield `(url, html|None)` per result.

        Uses Crawl4AI's native streaming dispatcher. `max_session_permit` is
        sized off `rate_limit_per_minute` so a 30/min cap maps to ~5 concurrent
        sessions — gentle enough that bursting doesn't break the cap.
        """
        streaming_config = self._run_config.clone(stream=True)
        dispatcher = MemoryAdaptiveDispatcher(
            memory_threshold_percent=85.0,
            max_session_permit=max(1, self._rate_limit_per_minute // 6),
        )

        async with AsyncWebCrawler(config=self._browser_config) as crawler:
            async for result in await crawler.arun_many(
                urls=urls,
                config=streaming_config,
                dispatcher=dispatcher,
            ):
                if result.success:
                    yield (result.url, result.html)
                else:
                    log.warning(
                        "crawl4ai stream-result failed: url=%s err=%s",
                        safe_url(result.url),
                        result.error_message,
                    )
                    yield (result.url, None)

    async def _respect_rate_limit(self) -> None:
        """Sleep so requests/minute stays under the cap; add jitter."""
        now = asyncio.get_running_loop().time()
        min_interval = 60.0 / max(1, self._rate_limit_per_minute)
        elapsed = now - self._last_request_at
        if elapsed < min_interval:
            await asyncio.sleep(min_interval - elapsed)
        jitter = random.uniform(*self._random_delay_seconds)
        await asyncio.sleep(jitter)
        self._last_request_at = asyncio.get_running_loop().time()
