"""Plan 64 § Build sequence commit 3 — LinkedIn + scheduler proxy wiring.

Asserts:
- `_scrape_one_user` resolves proxy via `resolve_proxy_config(JobSource.LINKEDIN)`
  and threads it into Crawl4AIClient construction.
- LinkedIn cron with env unset logs the boot warning ONCE.
- `scraper_service.run_scraper` writes `raw_meta.proxy` sub-key reflecting
  whether the proxy was active.
- The proxy host in raw_meta is REDACTED (no userinfo).
- Non-LinkedIn sources never see a proxy (resolver returns None).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from models import JobScrapeStatus, JobSource

pytestmark = pytest.mark.uses_sample_data_shims


def _make_settings(*, user_id: int = 1, **kw) -> SimpleNamespace:
    return SimpleNamespace(
        user_id=user_id,
        sources_enabled=kw.get("sources_enabled", {}),
        consecutive_scrape_failures=kw.get("consecutive_scrape_failures", {}),
        workday_companies=kw.get("workday_companies", []),
        linkedin_keywords=kw.get("linkedin_keywords"),
        linkedin_location=kw.get("linkedin_location"),
        indeed_keywords=kw.get("indeed_keywords"),
        indeed_location=kw.get("indeed_location"),
        notify_on_errors=True,
        notify_threshold=0.8,
        notifications_enabled={},
        llm_provider=None,
        llm_model="m",
        llm_fallback_provider=None,
        scraper_rate_limits={},
    )


class _FakeSession:
    def __init__(self) -> None:
        self.added: list = []
        self.exec_results: list = []
        self.flush_count = 0
        self.commit_count = 0
        self.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flush_count += 1

    async def commit(self):
        self.commit_count += 1

    async def exec(self, _stmt):
        if not self.exec_results:
            return SimpleNamespace(one_or_none=lambda: None, all=lambda: [], one=lambda: 0)
        return self.exec_results.pop(0)


# ── Scheduler threads proxy into Crawl4AIClient ───────────────────────────


@pytest.mark.asyncio
async def test_scheduler_threads_proxy_into_client_when_env_set(monkeypatch):
    """LINKEDIN_PROXY_URL set → Crawl4AIClient receives proxy_config."""
    from config import settings as app_settings
    from scheduler import scraping

    captured = {}

    class _CapturingClient:
        def __init__(self, **kw):
            captured["proxy_config"] = kw.get("proxy_config")
            self.rate_limit_hits = 0
            self.backoff_total_s = 0.0
            self.user_agent = "test-ua"
            self.proxy_request_count = 0
            self.proxy_bytes_estimated = 0
            self.proxy_config = kw.get("proxy_config")

    async def fake_run_scraper(session, *, scraper, user_id, query, triggered_by):
        return SimpleNamespace(status=JobScrapeStatus.SUCCESS)

    monkeypatch.setattr(app_settings, "linkedin_proxy_url", "http://u:p@gate.example.com:7000")
    monkeypatch.setattr(app_settings, "linkedin_proxy_provider_hint", "smartproxy")
    monkeypatch.setattr(scraping, "Crawl4AIClient", _CapturingClient)
    monkeypatch.setattr(scraping, "run_scraper", fake_run_scraper)
    monkeypatch.setattr(scraping, "llm_get_provider", lambda _s: None)

    s = _make_settings(linkedin_keywords=["swe"])
    session = _FakeSession()
    await scraping._scrape_one_user(session, settings=s, source=JobSource.LINKEDIN)

    assert captured["proxy_config"] is not None
    assert captured["proxy_config"].url == "http://u:p@gate.example.com:7000"


@pytest.mark.asyncio
async def test_scheduler_no_proxy_when_env_unset(monkeypatch, caplog):
    """LINKEDIN_PROXY_URL unset → Crawl4AIClient receives None + warning fires."""
    import logging

    from config import settings as app_settings
    from scheduler import scraping

    captured = {}

    class _CapturingClient:
        def __init__(self, **kw):
            captured["proxy_config"] = kw.get("proxy_config")
            self.rate_limit_hits = 0
            self.backoff_total_s = 0.0
            self.user_agent = "test-ua"
            self.proxy_request_count = 0
            self.proxy_bytes_estimated = 0
            self.proxy_config = kw.get("proxy_config")

    async def fake_run_scraper(session, *, scraper, user_id, query, triggered_by):
        return SimpleNamespace(status=JobScrapeStatus.SUCCESS)

    monkeypatch.setattr(app_settings, "linkedin_proxy_url", None)
    monkeypatch.setattr(app_settings, "linkedin_proxy_provider_hint", None)
    monkeypatch.setattr(scraping, "Crawl4AIClient", _CapturingClient)
    monkeypatch.setattr(scraping, "run_scraper", fake_run_scraper)
    monkeypatch.setattr(scraping, "llm_get_provider", lambda _s: None)
    # Reset the once-flag so the warning fires.
    monkeypatch.setattr(scraping, "_LINKEDIN_PROXY_WARNED", False)

    s = _make_settings(linkedin_keywords=["swe"])
    session = _FakeSession()
    with caplog.at_level(logging.WARNING, logger="scheduler.scraping"):
        await scraping._scrape_one_user(session, settings=s, source=JobSource.LINKEDIN)

    assert captured["proxy_config"] is None
    assert any("LINKEDIN_PROXY_URL not set" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_scheduler_warning_only_fires_once_per_process(monkeypatch, caplog):
    """The boot warning fires ONCE — not per cron firing."""
    import logging

    from config import settings as app_settings
    from scheduler import scraping

    class _NoOpClient:
        def __init__(self, **kw):
            self.rate_limit_hits = 0
            self.backoff_total_s = 0.0
            self.user_agent = "test"
            self.proxy_request_count = 0
            self.proxy_bytes_estimated = 0
            self.proxy_config = None

    async def fake_run_scraper(session, *, scraper, user_id, query, triggered_by):
        return SimpleNamespace(status=JobScrapeStatus.SUCCESS)

    monkeypatch.setattr(app_settings, "linkedin_proxy_url", None)
    monkeypatch.setattr(app_settings, "linkedin_proxy_provider_hint", None)
    monkeypatch.setattr(scraping, "Crawl4AIClient", _NoOpClient)
    monkeypatch.setattr(scraping, "run_scraper", fake_run_scraper)
    monkeypatch.setattr(scraping, "llm_get_provider", lambda _s: None)
    monkeypatch.setattr(scraping, "_LINKEDIN_PROXY_WARNED", False)

    s = _make_settings(linkedin_keywords=["swe"])
    session = _FakeSession()
    with caplog.at_level(logging.WARNING, logger="scheduler.scraping"):
        # Two firings — second must NOT log the warning.
        await scraping._scrape_one_user(session, settings=s, source=JobSource.LINKEDIN)
        await scraping._scrape_one_user(session, settings=s, source=JobSource.LINKEDIN)

    warning_count = sum(1 for rec in caplog.records if "LINKEDIN_PROXY_URL not set" in rec.message)
    assert warning_count == 1


@pytest.mark.asyncio
async def test_scheduler_non_linkedin_source_never_gets_proxy(monkeypatch):
    """Plan 64 § D.7 — Greenhouse/Workday/etc. always get proxy=None."""
    from config import settings as app_settings
    from scheduler import scraping

    captured: dict = {}

    class _CapturingClient:
        def __init__(self, **kw):
            captured.setdefault("proxy_configs", []).append(kw.get("proxy_config"))
            self.rate_limit_hits = 0
            self.backoff_total_s = 0.0
            self.user_agent = "ua"
            self.proxy_request_count = 0
            self.proxy_bytes_estimated = 0
            self.proxy_config = kw.get("proxy_config")

    async def fake_run_scraper(session, *, scraper, user_id, query, triggered_by):
        return SimpleNamespace(status=JobScrapeStatus.SUCCESS)

    # Set the env var (which only LinkedIn reads); other sources still get None.
    monkeypatch.setattr(app_settings, "linkedin_proxy_url", "http://u:p@gate.example.com:7000")
    monkeypatch.setattr(app_settings, "linkedin_proxy_provider_hint", None)
    monkeypatch.setattr(scraping, "Crawl4AIClient", _CapturingClient)
    monkeypatch.setattr(scraping, "run_scraper", fake_run_scraper)
    monkeypatch.setattr(scraping, "llm_get_provider", lambda _s: None)
    # Sources must be configured or `_scrape_one_user` skips before the
    # client is constructed (unconfigured-source guard).
    monkeypatch.setattr(app_settings, "greenhouse_companies", ["acme"])
    monkeypatch.setattr(app_settings, "lever_companies", ["acme"])
    monkeypatch.setattr(app_settings, "ashby_companies", ["acme"])

    s = _make_settings(indeed_keywords=["swe"])
    session = _FakeSession()
    for src in (JobSource.GREENHOUSE, JobSource.LEVER, JobSource.ASHBY, JobSource.INDEED):
        await scraping._scrape_one_user(session, settings=s, source=src)

    assert all(p is None for p in captured["proxy_configs"])


# ── scraper_service writes raw_meta.proxy sub-key ─────────────────────────


@pytest.mark.asyncio
async def test_scraper_service_writes_proxy_sub_key_when_proxy_active(monkeypatch):
    """Plan 64 § D.9 — proxy telemetry in JobScrapeRun.raw_meta."""
    from scraper.crawl4ai_client import Crawl4AIClient
    from scraper.proxy import ProxyURLConfig
    from scraper.sites.sample import SampleScraper
    from services import jobs as job_service
    from services.jobs import scraping as scraper_service

    proxy_cfg = ProxyURLConfig(
        url="http://leaku:leakp@gate.example.com:7000",
        provider_hint="smartproxy",
    )

    class _SampleSession:
        def __init__(self):
            self.added = []
            self.flush_count = 0
            self.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
            self._jobs: dict = {}

        def add(self, obj):
            self.added.append(obj)

        async def flush(self):
            self.flush_count += 1

        async def exec(self, _stmt):
            return SimpleNamespace(one_or_none=lambda: None, all=lambda: [])

    client = Crawl4AIClient(
        random_delay_seconds=(0.0, 0.0),
        rate_limit_per_minute=1_000_000,
        proxy_config=proxy_cfg,
    )
    # Manually bump counters to simulate post-stream state.
    client.proxy_request_count = 5
    client.proxy_bytes_estimated = 12345

    scraper = SampleScraper(client=client)
    session = _SampleSession()

    fake_run = SimpleNamespace(
        id=1,
        status=JobScrapeStatus.RUNNING,
        finished_at=None,
        started_at=None,
        listings_returned=0,
        new_jobs=0,
        updated_jobs=0,
        errors=[],
        duration_ms=0,
        raw_meta={"scraper_name": "SampleScraper", "query": {}},
    )

    async def fake_record(*a, **kw):
        fake_run.started_at = kw.get("started_at")
        return fake_run

    async def fake_upsert(*a, **kw):
        return (SimpleNamespace(id=1), True)

    monkeypatch.setattr(job_service, "record_scrape_run", fake_record)
    monkeypatch.setattr(job_service, "upsert_job", fake_upsert)

    run = await scraper_service.run_scraper(
        session,  # type: ignore[arg-type]
        scraper=scraper,
        user_id=1,
        notify=False,
    )

    proxy_meta = run.raw_meta.get("proxy")
    assert proxy_meta is not None
    assert proxy_meta["used"] is True
    assert proxy_meta["host"] == "gate.example.com:7000"
    assert proxy_meta["provider_hint"] == "smartproxy"
    assert proxy_meta["request_count"] == 5
    assert proxy_meta["bytes_estimated"] == 12345
    # Credentials never appear anywhere in raw_meta.
    assert "leaku" not in str(proxy_meta)
    assert "leakp" not in str(proxy_meta)


@pytest.mark.asyncio
async def test_scraper_service_writes_proxy_used_false_when_no_proxy(monkeypatch):
    """No proxy → raw_meta.proxy.used is False + host is None."""
    from scraper.crawl4ai_client import Crawl4AIClient
    from scraper.sites.sample import SampleScraper
    from services import jobs as job_service
    from services.jobs import scraping as scraper_service

    class _SampleSession:
        def __init__(self):
            self.added = []
            self.flush_count = 0
            self.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

        def add(self, obj):
            self.added.append(obj)

        async def flush(self):
            self.flush_count += 1

        async def exec(self, _stmt):
            return SimpleNamespace(one_or_none=lambda: None, all=lambda: [])

    client = Crawl4AIClient(random_delay_seconds=(0.0, 0.0), rate_limit_per_minute=1_000_000)
    scraper = SampleScraper(client=client)
    session = _SampleSession()

    fake_run = SimpleNamespace(
        id=1,
        status=JobScrapeStatus.RUNNING,
        finished_at=None,
        started_at=None,
        listings_returned=0,
        new_jobs=0,
        updated_jobs=0,
        errors=[],
        duration_ms=0,
        raw_meta={"scraper_name": "SampleScraper", "query": {}},
    )

    async def fake_record(*a, **kw):
        fake_run.started_at = kw.get("started_at")
        return fake_run

    async def fake_upsert(*a, **kw):
        return (SimpleNamespace(id=1), True)

    monkeypatch.setattr(job_service, "record_scrape_run", fake_record)
    monkeypatch.setattr(job_service, "upsert_job", fake_upsert)

    run = await scraper_service.run_scraper(
        session,  # type: ignore[arg-type]
        scraper=scraper,
        user_id=1,
        notify=False,
    )

    proxy_meta = run.raw_meta.get("proxy")
    assert proxy_meta is not None
    assert proxy_meta["used"] is False
    assert proxy_meta["host"] is None
    assert proxy_meta["provider_hint"] is None
    assert proxy_meta["request_count"] == 0
    assert proxy_meta["bytes_estimated"] == 0
