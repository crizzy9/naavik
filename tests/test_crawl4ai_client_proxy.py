"""Plan 64 § Build sequence commit 2 — Crawl4AIClient proxy pass-through tests.

Asserts:
- `Crawl4AIClient.__init__(proxy_config=...)` threads the ProxyConfig into
  `self._run_config.proxy_config` (Crawl4AI 0.8.6's per-request slot).
- `proxy_config=None` keeps the construction path unchanged (no proxy).
- `proxy_bytes_estimated` + `proxy_request_count` counters increment on
  successful fetches when proxy is active, stay zero otherwise.
- Fail-loud failover behavior (plan 64 § D.6): TimeoutError / connection
  refused from arun propagates — no degrade-to-direct.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.uses_sample_data_shims


@pytest.fixture(autouse=True)
def _stub_url_guard_dns(monkeypatch):
    from scraper import url_guard

    monkeypatch.setattr(url_guard, "_resolve_host", lambda host: ("93.184.216.34",))
    url_guard._DNS_CACHE.clear()


class _FakeAsyncCrawler:
    def __init__(self, *, arun_result=None, arun_many_results=None, arun_raises=None) -> None:
        self.arun_result = arun_result
        self.arun_many_results = arun_many_results or []
        self.arun_raises = arun_raises
        self.arun_calls: list = []
        self.arun_many_calls: list = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def arun(self, *, url, config):
        self.arun_calls.append({"url": url, "config": config})
        if self.arun_raises is not None:
            raise self.arun_raises
        return self.arun_result

    async def arun_many(self, *, urls, config, dispatcher):
        self.arun_many_calls.append({"urls": urls, "config": config, "dispatcher": dispatcher})

        async def _gen():
            for r in self.arun_many_results:
                yield r

        return _gen()


def _result(url, html, success=True, error=None):
    return SimpleNamespace(url=url, html=html, success=success, error_message=error)


# ── Constructor + run_config wiring ───────────────────────────────────────


def test_constructor_with_proxy_config_threads_to_run_config():
    from scraper.crawl4ai_client import Crawl4AIClient
    from scraper.proxy import ProxyURLConfig

    pc = ProxyURLConfig(url="http://user:pass@gate.example.com:7000")
    client = Crawl4AIClient(proxy_config=pc, random_delay_seconds=(0.0, 0.0))

    # Public accessor surfaces what was passed.
    assert client.proxy_config is pc
    # The Crawl4AI ProxyConfig lives on the per-request CrawlerRunConfig.
    assert client._run_config.proxy_config is not None
    assert client._run_config.proxy_config.server == "http://gate.example.com:7000"


def test_constructor_without_proxy_config_leaves_run_config_unmodified():
    from scraper.crawl4ai_client import Crawl4AIClient

    client = Crawl4AIClient(random_delay_seconds=(0.0, 0.0))
    assert client.proxy_config is None
    assert client._run_config.proxy_config is None


# ── proxy_bytes_estimated + proxy_request_count counters ──────────────────


@pytest.mark.asyncio
async def test_fetch_html_increments_proxy_counters_when_proxy_active(monkeypatch):
    from scraper.crawl4ai_client import Crawl4AIClient
    from scraper.proxy import ProxyURLConfig

    fake = _FakeAsyncCrawler(
        arun_result=_result(url="https://example.com/jobs/1", html="<html>1234567890</html>")
    )
    monkeypatch.setattr("scraper.crawl4ai_client.AsyncWebCrawler", lambda **_: fake)

    pc = ProxyURLConfig(url="http://u:p@gate.example.com:7000")
    client = Crawl4AIClient(
        proxy_config=pc, random_delay_seconds=(0.0, 0.0), rate_limit_per_minute=1_000_000
    )
    html = await client.fetch_html("https://example.com/jobs/1")

    assert html == "<html>1234567890</html>"
    assert client.proxy_request_count == 1
    assert client.proxy_bytes_estimated == len("<html>1234567890</html>")


@pytest.mark.asyncio
async def test_fetch_html_does_not_increment_proxy_counters_when_no_proxy(monkeypatch):
    """No proxy configured → counters stay 0 even on successful fetch."""
    from scraper.crawl4ai_client import Crawl4AIClient

    fake = _FakeAsyncCrawler(
        arun_result=_result(url="https://example.com/jobs/1", html="<html>some-data</html>")
    )
    monkeypatch.setattr("scraper.crawl4ai_client.AsyncWebCrawler", lambda **_: fake)

    client = Crawl4AIClient(random_delay_seconds=(0.0, 0.0), rate_limit_per_minute=1_000_000)
    await client.fetch_html("https://example.com/jobs/1")

    assert client.proxy_request_count == 0
    assert client.proxy_bytes_estimated == 0


@pytest.mark.asyncio
async def test_stream_many_increments_proxy_counters_per_success(monkeypatch):
    from scraper.crawl4ai_client import Crawl4AIClient
    from scraper.proxy import ProxyURLConfig

    fake = _FakeAsyncCrawler(
        arun_many_results=[
            _result(url="https://a.com/1", html="<a>11</a>"),
            _result(url="https://a.com/2", html="<a>22</a>"),
            _result(url="https://a.com/3", html=None, success=False, error="403"),
        ]
    )
    monkeypatch.setattr("scraper.crawl4ai_client.AsyncWebCrawler", lambda **_: fake)

    pc = ProxyURLConfig(url="http://u:p@gate.example.com:7000")
    client = Crawl4AIClient(
        proxy_config=pc, random_delay_seconds=(0.0, 0.0), rate_limit_per_minute=1_000_000
    )
    results = [
        pair
        async for pair in client.stream_many(
            ["https://a.com/1", "https://a.com/2", "https://a.com/3"]
        )
    ]

    # 3 results, 2 successful.
    assert len(results) == 3
    assert client.proxy_request_count == 2
    assert client.proxy_bytes_estimated == len("<a>11</a>") + len("<a>22</a>")


@pytest.mark.asyncio
async def test_fetch_html_propagates_proxy_failure_no_degrade_to_direct(monkeypatch):
    """Plan 64 § D.6 — fail-loud. TimeoutError from arun must propagate."""
    from scraper.crawl4ai_client import Crawl4AIClient
    from scraper.proxy import ProxyURLConfig

    fake = _FakeAsyncCrawler(arun_raises=TimeoutError("proxy connect timeout"))
    monkeypatch.setattr("scraper.crawl4ai_client.AsyncWebCrawler", lambda **_: fake)

    pc = ProxyURLConfig(url="http://u:p@gate.example.com:7000")
    client = Crawl4AIClient(
        proxy_config=pc, random_delay_seconds=(0.0, 0.0), rate_limit_per_minute=1_000_000
    )
    # The exception MUST propagate — Crawl4AIClient does NOT catch it +
    # silently retry without the proxy.
    with pytest.raises(asyncio.TimeoutError):
        await client.fetch_html("https://example.com/jobs/1")


@pytest.mark.asyncio
async def test_stream_many_propagates_proxy_failure_no_degrade_to_direct(monkeypatch):
    """Plan 64 § D.6 — fail-loud for the batch path too."""
    from scraper.crawl4ai_client import Crawl4AIClient
    from scraper.proxy import ProxyURLConfig

    class _RaisingCrawler:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def arun_many(self, *, urls, config, dispatcher):
            raise ConnectionError("proxy connection refused")

    monkeypatch.setattr("scraper.crawl4ai_client.AsyncWebCrawler", lambda **_: _RaisingCrawler())

    pc = ProxyURLConfig(url="http://u:p@gate.example.com:7000")
    client = Crawl4AIClient(
        proxy_config=pc, random_delay_seconds=(0.0, 0.0), rate_limit_per_minute=1_000_000
    )
    with pytest.raises(ConnectionError):
        async for _ in client.stream_many(["https://example.com/1"]):
            pass
