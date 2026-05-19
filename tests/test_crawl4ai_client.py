"""Crawl4AIClient tests — plan 29 § D.9.

Mocks `crawl4ai.AsyncWebCrawler` (async context manager) + canned
`CrawlResult` stand-ins. No real Chromium is launched.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

# ── Async-CM stand-in for AsyncWebCrawler ────────────────────────────────


class _FakeAsyncCrawler:
    """Stands in for `AsyncWebCrawler(config=...)` async context manager."""

    def __init__(self, *, arun_result=None, arun_many_results=None) -> None:
        self.arun_result = arun_result
        self.arun_many_results = arun_many_results or []
        self.arun_calls: list[dict] = []
        self.arun_many_calls: list[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def arun(self, *, url, config):
        self.arun_calls.append({"url": url, "config": config})
        return self.arun_result

    async def arun_many(self, *, urls, config, dispatcher):
        self.arun_many_calls.append({"urls": urls, "config": config, "dispatcher": dispatcher})

        async def _gen():
            for r in self.arun_many_results:
                yield r

        return _gen()


def _fake_crawl_result(url: str, html: str | None, success: bool = True, error: str | None = None):
    return SimpleNamespace(
        url=url,
        html=html,
        success=success,
        error_message=error,
    )


# ── fetch_html ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_html_returns_html_on_success(monkeypatch):
    from scraper.crawl4ai_client import Crawl4AIClient

    fake = _FakeAsyncCrawler(
        arun_result=_fake_crawl_result(
            url="https://example.com/jobs/1",
            html="<html><body>hi</body></html>",
            success=True,
        )
    )
    monkeypatch.setattr("scraper.crawl4ai_client.AsyncWebCrawler", lambda **_kw: fake)

    client = Crawl4AIClient(random_delay_seconds=(0.0, 0.0), rate_limit_per_minute=1_000_000)
    html = await client.fetch_html("https://example.com/jobs/1")

    assert html == "<html><body>hi</body></html>"
    assert len(fake.arun_calls) == 1
    assert fake.arun_calls[0]["url"] == "https://example.com/jobs/1"


@pytest.mark.asyncio
async def test_fetch_html_returns_none_on_failure(monkeypatch):
    from scraper.crawl4ai_client import Crawl4AIClient

    fake = _FakeAsyncCrawler(
        arun_result=_fake_crawl_result(
            url="https://example.com/jobs/2",
            html=None,
            success=False,
            error="403 Forbidden",
        )
    )
    monkeypatch.setattr("scraper.crawl4ai_client.AsyncWebCrawler", lambda **_kw: fake)

    client = Crawl4AIClient(random_delay_seconds=(0.0, 0.0), rate_limit_per_minute=1_000_000)
    html = await client.fetch_html("https://example.com/jobs/2")

    assert html is None


# ── stream_many ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stream_many_yields_each_result(monkeypatch):
    from scraper.crawl4ai_client import Crawl4AIClient

    fake = _FakeAsyncCrawler(
        arun_many_results=[
            _fake_crawl_result(url="https://a.com/1", html="<a>1</a>", success=True),
            _fake_crawl_result(url="https://a.com/2", html="<a>2</a>", success=True),
        ]
    )
    monkeypatch.setattr("scraper.crawl4ai_client.AsyncWebCrawler", lambda **_kw: fake)

    client = Crawl4AIClient(random_delay_seconds=(0.0, 0.0), rate_limit_per_minute=1_000_000)
    results = [pair async for pair in client.stream_many(["https://a.com/1", "https://a.com/2"])]

    assert results == [
        ("https://a.com/1", "<a>1</a>"),
        ("https://a.com/2", "<a>2</a>"),
    ]


@pytest.mark.asyncio
async def test_stream_many_yields_none_for_failed_url(monkeypatch):
    from scraper.crawl4ai_client import Crawl4AIClient

    fake = _FakeAsyncCrawler(
        arun_many_results=[
            _fake_crawl_result(url="https://a.com/1", html="<a>1</a>", success=True),
            _fake_crawl_result(url="https://a.com/2", html=None, success=False, error="timeout"),
        ]
    )
    monkeypatch.setattr("scraper.crawl4ai_client.AsyncWebCrawler", lambda **_kw: fake)

    client = Crawl4AIClient(random_delay_seconds=(0.0, 0.0), rate_limit_per_minute=1_000_000)
    results = [pair async for pair in client.stream_many(["https://a.com/1", "https://a.com/2"])]

    assert results == [
        ("https://a.com/1", "<a>1</a>"),
        ("https://a.com/2", None),
    ]


@pytest.mark.asyncio
async def test_stream_many_passes_stream_true_in_config(monkeypatch):
    from scraper.crawl4ai_client import Crawl4AIClient

    fake = _FakeAsyncCrawler(arun_many_results=[])
    monkeypatch.setattr("scraper.crawl4ai_client.AsyncWebCrawler", lambda **_kw: fake)

    client = Crawl4AIClient(random_delay_seconds=(0.0, 0.0), rate_limit_per_minute=1_000_000)
    async for _ in client.stream_many(["https://a.com/1"]):  # pragma: no cover
        pass

    assert len(fake.arun_many_calls) == 1
    call = fake.arun_many_calls[0]
    assert call["config"].stream is True
    assert call["urls"] == ["https://a.com/1"]


# ── Rate-limit helper ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_respect_rate_limit_sleeps_for_min_interval(monkeypatch):
    """A 60 req/min cap means min interval = 1s; first call jitter only."""
    from scraper import crawl4ai_client as mod

    sleep_calls: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr(mod.asyncio, "sleep", _fake_sleep)
    monkeypatch.setattr(mod.random, "uniform", lambda lo, hi: 0.5)
    # Freeze time at 0 then 0 (no elapsed); rate_limit=60 → min_interval=1s.
    fake_loop = MagicMock()
    fake_loop.time.return_value = 0.0
    monkeypatch.setattr(mod.asyncio, "get_event_loop", lambda: fake_loop)

    client = mod.Crawl4AIClient(
        rate_limit_per_minute=60,
        random_delay_seconds=(0.5, 0.5),
    )
    # Prime: simulate a prior call so elapsed < min_interval triggers the
    # "wait for the rest of the interval" branch.
    client._last_request_at = 0.0
    fake_loop.time.return_value = 0.2  # 0.2s after last request
    await client._respect_rate_limit()

    # First sleep is the "wait for rest of interval" (1.0 - 0.2 = 0.8s);
    # second sleep is the jitter (0.5s frozen).
    assert sleep_calls == [pytest.approx(0.8), pytest.approx(0.5)]


@pytest.mark.asyncio
async def test_respect_rate_limit_no_wait_when_interval_already_elapsed(monkeypatch):
    """If enough time has passed, only the jitter sleep fires."""
    from scraper import crawl4ai_client as mod

    sleep_calls: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr(mod.asyncio, "sleep", _fake_sleep)
    monkeypatch.setattr(mod.random, "uniform", lambda lo, hi: 1.2)
    fake_loop = MagicMock()
    fake_loop.time.return_value = 10.0  # 10s after last; well past 1s interval
    monkeypatch.setattr(mod.asyncio, "get_event_loop", lambda: fake_loop)

    client = mod.Crawl4AIClient(
        rate_limit_per_minute=60,
        random_delay_seconds=(1.2, 1.2),
    )
    client._last_request_at = 0.0
    await client._respect_rate_limit()

    assert sleep_calls == [pytest.approx(1.2)]


# ── Constructor wiring ────────────────────────────────────────────────────


def test_constructor_propagates_browser_flags():
    from scraper.crawl4ai_client import Crawl4AIClient

    client = Crawl4AIClient(enable_stealth=False, headless=False)
    assert client._browser_config.enable_stealth is False
    assert client._browser_config.headless is False
