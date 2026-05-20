"""Crawl4AIClient tests — plan 29 § D.9.

Mocks `crawl4ai.AsyncWebCrawler` (async context manager) + canned
`CrawlResult` stand-ins. No real Chromium is launched.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _stub_url_guard_dns(monkeypatch):
    """Force the url-guard DNS resolver to a public IP for all test hosts.

    `Crawl4AIClient.{fetch_html,stream_many}` consults
    `scraper.url_guard.is_safe_destination` (plan 33 § D.5) on every URL.
    The guard's RFC1918 / IMDS denylist is keyed off DNS resolution; in CI
    we want the guard to return `(True, None)` for anything that's not an
    explicitly hostile host so existing tests stay focused on Crawl4AI's
    HttpUrl gate + the rate-limit logic.
    """
    from scraper import url_guard

    def fake_resolve(host: str) -> tuple[str, ...]:
        # Public-looking IP; not in any deny network.
        return ("93.184.216.34",)

    monkeypatch.setattr(url_guard, "_resolve_host", fake_resolve)
    url_guard._DNS_CACHE.clear()


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
async def test_enforce_min_interval_sleeps_for_min_interval(monkeypatch):
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
    monkeypatch.setattr(mod.asyncio, "get_running_loop", lambda: fake_loop)

    client = mod.Crawl4AIClient(
        rate_limit_per_minute=60,
        random_delay_seconds=(0.5, 0.5),
    )
    # Prime: simulate a prior call so elapsed < min_interval triggers the
    # "wait for the rest of the interval" branch.
    client._last_request_at = 0.0
    fake_loop.time.return_value = 0.2  # 0.2s after last request
    await client._enforce_min_interval()

    # First sleep is the "wait for rest of interval" (1.0 - 0.2 = 0.8s);
    # second sleep is the jitter (0.5s frozen).
    assert sleep_calls == [pytest.approx(0.8), pytest.approx(0.5)]


@pytest.mark.asyncio
async def test_enforce_min_interval_no_wait_when_interval_already_elapsed(monkeypatch):
    """If enough time has passed, only the jitter sleep fires."""
    from scraper import crawl4ai_client as mod

    sleep_calls: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr(mod.asyncio, "sleep", _fake_sleep)
    monkeypatch.setattr(mod.random, "uniform", lambda lo, hi: 1.2)
    fake_loop = MagicMock()
    fake_loop.time.return_value = 10.0  # 10s after last; well past 1s interval
    monkeypatch.setattr(mod.asyncio, "get_running_loop", lambda: fake_loop)

    client = mod.Crawl4AIClient(
        rate_limit_per_minute=60,
        random_delay_seconds=(1.2, 1.2),
    )
    client._last_request_at = 0.0
    await client._enforce_min_interval()

    assert sleep_calls == [pytest.approx(1.2)]


# ── Constructor wiring ────────────────────────────────────────────────────


def test_constructor_propagates_browser_flags():
    from scraper.crawl4ai_client import Crawl4AIClient

    client = Crawl4AIClient(enable_stealth=False, headless=False)
    assert client._browser_config.enable_stealth is False
    assert client._browser_config.headless is False


# ── SSRF/LFI scheme allowlist (plan 31 D.1) ──────────────────────────────


@pytest.mark.asyncio
async def test_fetch_html_rejects_file_scheme(monkeypatch, caplog):
    from scraper.crawl4ai_client import Crawl4AIClient

    fake = _FakeAsyncCrawler(arun_result=_fake_crawl_result(url="x", html="x"))
    monkeypatch.setattr("scraper.crawl4ai_client.AsyncWebCrawler", lambda **_kw: fake)

    client = Crawl4AIClient(random_delay_seconds=(0.0, 0.0), rate_limit_per_minute=1_000_000)
    with caplog.at_level("WARNING", logger="scraper.crawl4ai_client"):
        html = await client.fetch_html("file:///etc/passwd")

    assert html is None
    assert fake.arun_calls == []
    assert any("rejected" in rec.message for rec in caplog.records)
    assert all(
        "/etc/passwd" not in rec.getMessage() or "scheme-blocked" in rec.getMessage()
        for rec in caplog.records
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "hostile_url",
    ["gopher://x:6379/_INFO", "ftp://example.com/jobs", "javascript:alert(1)", "not a url"],
)
async def test_fetch_html_rejects_gopher_and_malformed(monkeypatch, hostile_url):
    from scraper.crawl4ai_client import Crawl4AIClient

    fake = _FakeAsyncCrawler(arun_result=_fake_crawl_result(url="x", html="x"))
    monkeypatch.setattr("scraper.crawl4ai_client.AsyncWebCrawler", lambda **_kw: fake)

    client = Crawl4AIClient(random_delay_seconds=(0.0, 0.0), rate_limit_per_minute=1_000_000)
    html = await client.fetch_html(hostile_url)

    assert html is None
    assert fake.arun_calls == []


# ── stream_many SSRF/LFI scheme allowlist (plan 32 D.1) ──────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "hostile_url",
    [
        "file:///etc/passwd",
        "ftp://x",
        "gopher://x:6379/_INFO",
        "javascript:alert(1)",
    ],
)
async def test_stream_many_rejects_non_http_urls(monkeypatch, caplog, hostile_url):
    """plan 32 D.1 — per-URL HttpUrl validation in stream_many."""
    from scraper.crawl4ai_client import Crawl4AIClient

    fake = _FakeAsyncCrawler(
        arun_many_results=[
            _fake_crawl_result(url="https://valid.com/1", html="<a>ok</a>", success=True),
        ]
    )
    monkeypatch.setattr("scraper.crawl4ai_client.AsyncWebCrawler", lambda **_kw: fake)

    client = Crawl4AIClient(random_delay_seconds=(0.0, 0.0), rate_limit_per_minute=1_000_000)
    with caplog.at_level("WARNING", logger="scraper.crawl4ai_client"):
        results = [pair async for pair in client.stream_many([hostile_url, "https://valid.com/1"])]

    # The hostile URL is rejected pre-arun_many; only the valid URL reaches Crawl4AI.
    assert results == [("https://valid.com/1", "<a>ok</a>")]
    assert len(fake.arun_many_calls) == 1
    assert fake.arun_many_calls[0]["urls"] == ["https://valid.com/1"]
    assert any("stream-many rejected" in rec.message for rec in caplog.records)


# ── Plan 38 — rate-limit telemetry + RateLimiter wiring ──────────────────


def _fake_crawl_result_with_status(
    url: str,
    *,
    html: str | None = None,
    success: bool = False,
    status_code: int | None = None,
    error: str | None = None,
):
    return SimpleNamespace(
        url=url,
        html=html,
        success=success,
        status_code=status_code,
        error_message=error,
    )


@pytest.mark.asyncio
async def test_fetch_html_increments_rate_limit_hits_on_429(monkeypatch):
    """A 429 response bumps `rate_limit_hits` counter for telemetry surface."""
    from scraper.crawl4ai_client import Crawl4AIClient

    fake = _FakeAsyncCrawler(
        arun_result=_fake_crawl_result_with_status(
            url="https://example.com/jobs/1",
            success=False,
            status_code=429,
            error="Too Many Requests",
        )
    )
    monkeypatch.setattr("scraper.crawl4ai_client.AsyncWebCrawler", lambda **_kw: fake)

    client = Crawl4AIClient(random_delay_seconds=(0.0, 0.0), rate_limit_per_minute=1_000_000)
    html = await client.fetch_html("https://example.com/jobs/1")

    assert html is None
    assert client.rate_limit_hits == 1


@pytest.mark.asyncio
async def test_fetch_html_increments_rate_limit_hits_on_503(monkeypatch):
    from scraper.crawl4ai_client import Crawl4AIClient

    fake = _FakeAsyncCrawler(
        arun_result=_fake_crawl_result_with_status(
            url="https://example.com/jobs/2",
            success=False,
            status_code=503,
            error="Service Unavailable",
        )
    )
    monkeypatch.setattr("scraper.crawl4ai_client.AsyncWebCrawler", lambda **_kw: fake)

    client = Crawl4AIClient(random_delay_seconds=(0.0, 0.0), rate_limit_per_minute=1_000_000)
    await client.fetch_html("https://example.com/jobs/2")
    assert client.rate_limit_hits == 1


@pytest.mark.asyncio
async def test_fetch_html_increments_rate_limit_hits_when_error_string_mentions_rate_limit(
    monkeypatch,
):
    """Fallback path: status_code absent, but error message says 'rate limit'."""
    from scraper.crawl4ai_client import Crawl4AIClient

    fake = _FakeAsyncCrawler(
        arun_result=_fake_crawl_result_with_status(
            url="https://example.com/jobs/3",
            success=False,
            error="rate limit exceeded — retry later",
        )
    )
    monkeypatch.setattr("scraper.crawl4ai_client.AsyncWebCrawler", lambda **_kw: fake)

    client = Crawl4AIClient(random_delay_seconds=(0.0, 0.0), rate_limit_per_minute=1_000_000)
    await client.fetch_html("https://example.com/jobs/3")
    assert client.rate_limit_hits == 1


@pytest.mark.asyncio
async def test_fetch_html_other_failures_dont_bump_rl_counter(monkeypatch):
    """A generic 404 should not look like rate-limiting."""
    from scraper.crawl4ai_client import Crawl4AIClient

    fake = _FakeAsyncCrawler(
        arun_result=_fake_crawl_result_with_status(
            url="https://example.com/jobs/4",
            success=False,
            status_code=404,
            error="Not Found",
        )
    )
    monkeypatch.setattr("scraper.crawl4ai_client.AsyncWebCrawler", lambda **_kw: fake)

    client = Crawl4AIClient(random_delay_seconds=(0.0, 0.0), rate_limit_per_minute=1_000_000)
    await client.fetch_html("https://example.com/jobs/4")
    assert client.rate_limit_hits == 0


@pytest.mark.asyncio
async def test_stream_many_passes_rate_limiter_to_dispatcher(monkeypatch):
    """`MemoryAdaptiveDispatcher(rate_limiter=...)` is wired with our instance."""
    from scraper.crawl4ai_client import Crawl4AIClient

    fake = _FakeAsyncCrawler(arun_many_results=[])
    monkeypatch.setattr("scraper.crawl4ai_client.AsyncWebCrawler", lambda **_kw: fake)

    client = Crawl4AIClient(random_delay_seconds=(0.5, 1.5), rate_limit_per_minute=10.0)
    async for _ in client.stream_many(["https://a.com/1"]):  # pragma: no cover
        pass

    assert len(fake.arun_many_calls) == 1
    dispatcher = fake.arun_many_calls[0]["dispatcher"]
    assert dispatcher.rate_limiter is client._rate_limiter
    assert dispatcher.rate_limiter.max_delay == 60.0
    assert dispatcher.rate_limiter.max_retries == 2
    assert 429 in dispatcher.rate_limiter.rate_limit_codes
    assert 503 in dispatcher.rate_limiter.rate_limit_codes


@pytest.mark.asyncio
async def test_stream_many_bumps_counter_on_429_result(monkeypatch):
    from scraper.crawl4ai_client import Crawl4AIClient

    fake = _FakeAsyncCrawler(
        arun_many_results=[
            _fake_crawl_result_with_status(
                url="https://a.com/1", success=False, status_code=429, error="429"
            ),
            _fake_crawl_result_with_status(url="https://a.com/2", html="<a>ok</a>", success=True),
        ]
    )
    monkeypatch.setattr("scraper.crawl4ai_client.AsyncWebCrawler", lambda **_kw: fake)

    client = Crawl4AIClient(random_delay_seconds=(0.0, 0.0), rate_limit_per_minute=1_000_000)
    results = [pair async for pair in client.stream_many(["https://a.com/1", "https://a.com/2"])]

    assert results == [("https://a.com/1", None), ("https://a.com/2", "<a>ok</a>")]
    assert client.rate_limit_hits == 1
    assert client.backoff_total_s >= 0.0


def test_constructor_records_user_agent_in_browser_config():
    """The pinned UA must thread into BrowserConfig (browser-level fingerprint)."""
    from scraper.crawl4ai_client import Crawl4AIClient

    pinned = "Mozilla/5.0 TestUA/1.0"
    client = Crawl4AIClient(user_agent=pinned)
    assert client._browser_config.user_agent == pinned


def test_use_undetected_adapter_off_uses_plain_crawler(monkeypatch):
    """`use_undetected_adapter=False` constructs a plain `AsyncWebCrawler`."""
    from scraper.crawl4ai_client import Crawl4AIClient

    constructed: list[dict] = []

    def _fake_crawler(**kwargs):
        constructed.append(kwargs)
        return _FakeAsyncCrawler(arun_result=_fake_crawl_result(url="x", html="ok"))

    monkeypatch.setattr("scraper.crawl4ai_client.AsyncWebCrawler", _fake_crawler)
    client = Crawl4AIClient(use_undetected_adapter=False)
    _ = client._make_crawler()

    assert len(constructed) == 1
    # Plain branch passes `config=`; undetected branch passes `crawler_strategy=`.
    assert "config" in constructed[0]
    assert "crawler_strategy" not in constructed[0]


def test_use_undetected_adapter_on_uses_playwright_strategy(monkeypatch):
    """`use_undetected_adapter=True` wires UndetectedAdapter via PlaywrightStrategy."""
    from scraper.crawl4ai_client import Crawl4AIClient

    constructed: list[dict] = []

    def _fake_crawler(**kwargs):
        constructed.append(kwargs)
        return _FakeAsyncCrawler(arun_result=_fake_crawl_result(url="x", html="ok"))

    monkeypatch.setattr("scraper.crawl4ai_client.AsyncWebCrawler", _fake_crawler)
    client = Crawl4AIClient(use_undetected_adapter=True)
    _ = client._make_crawler()

    assert len(constructed) == 1
    assert "crawler_strategy" in constructed[0]
    assert "config" not in constructed[0]


def test_rate_limit_per_minute_accepts_float():
    """Plan 38 § D.8: int → float so LinkedIn 0.4 no longer floors to 1."""
    from scraper.crawl4ai_client import Crawl4AIClient

    client = Crawl4AIClient(rate_limit_per_minute=0.4)
    # 60 / 0.4 = 150s between requests.
    assert client._min_interval_s == pytest.approx(150.0)


def test_rate_limit_per_minute_floors_below_zero_one():
    """rpm=0 would deadlock; max(0.1, ...) caps min_interval at 600s."""
    from scraper.crawl4ai_client import Crawl4AIClient

    client = Crawl4AIClient(rate_limit_per_minute=0.0)
    assert client._min_interval_s == pytest.approx(600.0)


def test_user_agent_property_exposes_pinned_string():
    from scraper.crawl4ai_client import Crawl4AIClient

    pinned = "Mozilla/5.0 PropertyTest"
    client = Crawl4AIClient(user_agent=pinned)
    assert client.user_agent == pinned
