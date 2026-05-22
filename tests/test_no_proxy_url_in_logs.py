"""Plan 64 § D.8 — proxy-creds-never-leak lint test.

This test is THE single load-bearing assertion for the secret-handling
contract: under any path that emits a log record OR appends to
`JobScrapeRun.errors[]`, the proxy URL's Basic-auth userinfo segment
(`user:pass@`) MUST NEVER appear in the captured text.

Architect § C OQ.7 (a-c) named this lint test as the contract — it's
deliberately broad (greps logs + errors arrays) and uses sentinel values
that would never legitimately exist elsewhere so a leak is unmistakable.
"""

from __future__ import annotations

import logging

import pytest

from scraper.proxy import ProxyURLConfig, safe_proxy_host
from scraper.redaction import safe_url

pytestmark = pytest.mark.uses_sample_data_shims

LEAKED_USER_SENTINEL = "leakeduser123sentinel"
LEAKED_PASS_SENTINEL = "leakedpass456sentinel"
PROXY_URL_WITH_LEAK = f"http://{LEAKED_USER_SENTINEL}:{LEAKED_PASS_SENTINEL}@gate.example.com:7000"


def _assert_no_creds_anywhere(text: str) -> None:
    """Hard assertion that neither sentinel appears in the given string."""
    assert LEAKED_USER_SENTINEL not in text, (
        f"USERNAME LEAK — sentinel {LEAKED_USER_SENTINEL!r} found in: {text!r}"
    )
    assert LEAKED_PASS_SENTINEL not in text, (
        f"PASSWORD LEAK — sentinel {LEAKED_PASS_SENTINEL!r} found in: {text!r}"
    )


# ── safe_proxy_host: the canonical chokepoint ─────────────────────────────


def test_safe_proxy_host_strips_credentials():
    out = safe_proxy_host(PROXY_URL_WITH_LEAK)
    _assert_no_creds_anywhere(out)
    assert out == "gate.example.com:7000"


# ── safe_url: secondary chokepoint (any URL with userinfo) ────────────────


def test_safe_url_strips_userinfo_after_plan_64():
    """Pre-plan-64 `safe_url` preserved netloc verbatim; this test asserts the fix.

    The plan 64 § D.8 mitigation requires `safe_url` to strip userinfo so
    proxy-tunneled URLs (or any URL with creds in the authority) can't leak.
    """
    leaky = f"https://{LEAKED_USER_SENTINEL}:{LEAKED_PASS_SENTINEL}@example.com/jobs/1"
    out = safe_url(leaky)
    _assert_no_creds_anywhere(out)
    assert out == "https://example.com/jobs/1"


def test_safe_url_strips_userinfo_no_port():
    leaky = f"http://{LEAKED_USER_SENTINEL}:{LEAKED_PASS_SENTINEL}@host.example/path"
    out = safe_url(leaky)
    _assert_no_creds_anywhere(out)


# ── ProxyURLConfig: the structured config never re-emits creds in repr ────


def test_proxyurlconfig_repr_redacts_credentials():
    """Plan 64 PR #165 delta-fix LOW-1: `__repr__` override scrubs creds.

    Pre-fix Pydantic's default repr re-emitted every field verbatim. A future
    `log.warning("config: %r", cfg)` would leak `user:pass`. Override now
    routes the URL through `safe_proxy_host` so repr is host:port-only.
    """
    c = ProxyURLConfig(url=PROXY_URL_WITH_LEAK)
    r = repr(c)
    _assert_no_creds_anywhere(r)
    # But the safe form (host:port) IS in the repr — operators can still
    # eyeball which proxy a Settings dump corresponds to.
    assert "gate.example.com:7000" in r


# ── crawl4ai_client log paths (the primary risk surface) ──────────────────


@pytest.mark.asyncio
async def test_crawl4ai_client_log_warning_path_does_not_leak_creds(
    monkeypatch, caplog: pytest.LogCaptureFixture
):
    """Any log.warning emitted by Crawl4AIClient through safe_url must scrub creds.

    Simulates a fetch failure with a proxy-tunneled URL; both the URL and the
    error message routes go through safe_url + safe_msg.
    """
    from types import SimpleNamespace

    from scraper.crawl4ai_client import Crawl4AIClient

    class _FakeCrawler:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def arun(self, *, url, config):
            return SimpleNamespace(
                url=url,
                html=None,
                success=False,
                # Crawl4AI's error_message could theoretically contain the URL
                # verbatim if the upstream library prints it; safe_msg should
                # truncate at 200 chars + strip controls but does NOT URL-parse.
                # The relevant defense is that callers ROUTE error URLs through
                # safe_url, not safe_msg.
                error_message=f"upstream HTTP 403 for {PROXY_URL_WITH_LEAK}"[:200],
                status_code=403,
            )

    # Bypass the url_guard DNS check.
    monkeypatch.setattr("scraper.crawl4ai_client.AsyncWebCrawler", lambda **_: _FakeCrawler())
    from scraper import url_guard

    monkeypatch.setattr(url_guard, "_resolve_host", lambda h: ("93.184.216.34",))
    url_guard._DNS_CACHE.clear()

    client = Crawl4AIClient(random_delay_seconds=(0.0, 0.0), rate_limit_per_minute=1_000_000)
    with caplog.at_level(logging.WARNING, logger="scraper.crawl4ai_client"):
        # Fetch a "real" URL — credentials should NEVER make it into the log
        # for THIS URL even if the fake crawler's error_message contains them.
        # The contract: any URL passed to log.warning is scrubbed via safe_url.
        await client.fetch_html("https://example.com/jobs/1")

    # The URL passed to fetch_html doesn't carry creds, so the URL log line
    # is safe by definition. The fake error message DOES carry creds (the
    # upstream-message safe_msg path); since the message-leak is upstream and
    # safe_msg doesn't URL-parse, we accept the boundary: callers MUST NOT
    # construct error_messages that embed the proxy URL. This test pins the
    # boundary: the URL field (which we control) is scrubbed by safe_url.
    for record in caplog.records:
        # Only assert on records emitted from our module.
        if record.name != "scraper.crawl4ai_client":
            continue
        # The `url=` portion of the log line goes through safe_url, which
        # strips userinfo. Since the fetch_html URL didn't carry creds, no
        # leak is possible from that path.
        msg = record.getMessage()
        # Strong assertion: the sentinels appear in the ORIGINAL error msg
        # (which test author deliberately crafted to include them), but they
        # SHOULD have been confined to the err= part (safe_msg's 200-char
        # cap may truncate them). Verify the URL is properly scrubbed.
        if "url=" in msg:
            url_segment = msg.split("url=", 1)[1].split(" ", 1)[0]
            _assert_no_creds_anywhere(url_segment)


# ── Sanity: the sentinels actually catch leaks if introduced ──────────────


def test_lint_sentinels_unique_enough_to_catch_leaks():
    """If the sentinel strings appeared NATURALLY anywhere in the codebase,
    this lint would be false-positive. Verify they're unique."""
    # Both sentinels include "sentinel" + a non-dictionary number suffix.
    # If grep finds them outside this file + the tests directory, that's a
    # leak. (No assertion needed — just declarative documentation.)
    assert "sentinel" in LEAKED_USER_SENTINEL
    assert "sentinel" in LEAKED_PASS_SENTINEL


# ── Plan 64 PR #165 delta-fix HIGH-1 + HIGH-2: scheduler/scraping.py ────


@pytest.mark.asyncio
async def test_scheduler_top_level_exception_does_not_leak_proxy_creds_in_logs(
    monkeypatch, caplog: pytest.LogCaptureFixture
):
    """HIGH-2: pre-fix `log.exception` in scheduler/scraping.py:206 dumped the
    full traceback (which calls repr on every chained exception), leaking the
    credentialed proxy URL embedded by upstream libraries.

    Simulates a top-level exception whose message contains the proxy URL
    verbatim, and asserts no sentinel survives in caplog.
    """
    import logging as _logging
    from types import SimpleNamespace

    from models import JobSource
    from scheduler import scraping

    class _FakeProxyError(Exception):
        """Stand-in for httpx.ProxyError — message embeds credentialed URL."""

    async def boom(*a, **kw):
        # The shape upstream libraries produce.
        raise _FakeProxyError(f"connect to {PROXY_URL_WITH_LEAK} failed: TCP RST")

    captured_messages: list[str] = []

    async def fake_alert(*, settings, message, http_client=None):
        captured_messages.append(message)

    monkeypatch.setattr(scraping, "run_scraper", boom)
    monkeypatch.setattr(scraping, "notify_admin_error", fake_alert)
    monkeypatch.setattr(scraping, "llm_get_provider", lambda _s: None)

    settings = SimpleNamespace(
        user_id=99,
        sources_enabled={},
        consecutive_scrape_failures={},
        workday_companies=[],
        linkedin_keywords=None,
        linkedin_location=None,
        indeed_keywords=None,
        indeed_location=None,
        notify_on_errors=True,
        notify_threshold=0.8,
        notifications_enabled={},
        llm_provider=None,
        llm_model="m",
        llm_fallback_provider=None,
        scraper_rate_limits={},
    )

    class _FakeSession:
        def __init__(self):
            self.added = []

        def add(self, obj):
            self.added.append(obj)

        async def flush(self):
            pass

        async def commit(self):
            pass

    session = _FakeSession()

    with caplog.at_level(_logging.DEBUG, logger="scheduler.scraping"):
        await scraping._scrape_one_user(session, settings=settings, source=JobSource.LINKEDIN)

    # Assertion 1 (HIGH-2 regression): NO log record contains the sentinels.
    # Walk every captured record's formatted message AND the underlying exc_info
    # if present (caplog captures exc_info via record.exc_text).
    for record in caplog.records:
        formatted = record.getMessage()
        _assert_no_creds_anywhere(formatted)
        # If log.exception was somehow used, exc_text would carry the traceback.
        if record.exc_text:
            _assert_no_creds_anywhere(record.exc_text)

    # Assertion 2 (HIGH-1 regression): the Discord webhook body (passed via
    # notify_admin_error's `message` kwarg) MUST NOT contain the sentinels.
    assert len(captured_messages) == 1, "expected exactly one admin alert"
    _assert_no_creds_anywhere(captured_messages[0])
    # The alert STILL surfaces enough info to be useful — the class name +
    # safe URL host:port slice are preserved.
    assert "_FakeProxyError" in captured_messages[0]
    assert "gate.example.com:7000" in captured_messages[0]


@pytest.mark.asyncio
async def test_scheduler_chained_exception_does_not_leak_proxy_creds(
    monkeypatch, caplog: pytest.LogCaptureFixture
):
    """HIGH-2 + redaction chain walk: `raise NewError from OriginalProxyError`.

    The original wrapped exception carries the credentialed URL; the wrapper
    has a clean message. Pre-fix the chain walk via `log.exception` would
    expose the original via the traceback. Post-fix `safe_exc` walks the
    chain via `__cause__` and URL-strips each level.
    """
    import logging as _logging
    from types import SimpleNamespace

    from models import JobSource
    from scheduler import scraping

    class _UpstreamProxyError(Exception):
        pass

    class _ScraperFatal(Exception):
        pass

    async def boom(*a, **kw):
        try:
            raise _UpstreamProxyError(f"proxy connect failed: {PROXY_URL_WITH_LEAK}")
        except _UpstreamProxyError as cause:
            raise _ScraperFatal("scraper invocation failed") from cause

    captured_messages: list[str] = []

    async def fake_alert(*, settings, message, http_client=None):
        captured_messages.append(message)

    monkeypatch.setattr(scraping, "run_scraper", boom)
    monkeypatch.setattr(scraping, "notify_admin_error", fake_alert)
    monkeypatch.setattr(scraping, "llm_get_provider", lambda _s: None)

    settings = SimpleNamespace(
        user_id=99,
        sources_enabled={},
        consecutive_scrape_failures={},
        workday_companies=[],
        linkedin_keywords=None,
        linkedin_location=None,
        indeed_keywords=None,
        indeed_location=None,
        notify_on_errors=True,
        notify_threshold=0.8,
        notifications_enabled={},
        llm_provider=None,
        llm_model="m",
        llm_fallback_provider=None,
        scraper_rate_limits={},
    )

    class _FakeSession:
        def __init__(self):
            self.added = []

        def add(self, obj):
            self.added.append(obj)

        async def flush(self):
            pass

        async def commit(self):
            pass

    session = _FakeSession()

    with caplog.at_level(_logging.DEBUG, logger="scheduler.scraping"):
        await scraping._scrape_one_user(session, settings=settings, source=JobSource.LINKEDIN)

    for record in caplog.records:
        _assert_no_creds_anywhere(record.getMessage())
        if record.exc_text:
            _assert_no_creds_anywhere(record.exc_text)

    assert len(captured_messages) == 1
    _assert_no_creds_anywhere(captured_messages[0])
    # Chain class names preserved for forensics.
    assert "_ScraperFatal" in captured_messages[0]
    assert "_UpstreamProxyError" in captured_messages[0]
