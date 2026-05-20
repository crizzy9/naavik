"""Plan 35 (0.2.0.10) — scheduler.scraping cron unit tests.

Per docs/plans/35-0.2.0.10-apscheduler.md § D.9. Exercises:

- `_compose_query` per-source shaping (ATS slugs vs LinkedIn/Indeed keywords).
- `_scrape_one_user` consecutive-FAIL counter + auto-skip threshold.
- `_scrape_one_user` provider=None graceful degradation on LLMProviderError.
- `_scrape_one_user` sources_enabled gating.
- `_scrape_one_user` failure-isolation between users.
- `register_scraping_jobs` job count + jitter + IntervalTrigger for Indeed.

Pattern matches `tests/test_scraper_service.py` — in-memory fake session
that captures `add()` + `flush()` + serves canned `exec()` results.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from llm.base import LLMProviderError
from models import (
    ApplicationBoard,
    JobScrapeStatus,
    JobSource,
)
from scheduler import scraping
from scraper.base import ScraperBase
from scraper.types import RawJob, ScrapeQuery

# ── In-memory Settings + Session fakes ─────────────────────────────────


def _make_settings(
    *,
    user_id: int = 1,
    sources_enabled: dict[str, bool] | None = None,
    consecutive_scrape_failures: dict[str, int] | None = None,
    workday_companies: list[str] | None = None,
    linkedin_keywords: list[str] | None = None,
    linkedin_location: str | None = None,
    indeed_keywords: list[str] | None = None,
    indeed_location: str | None = None,
    notify_on_errors: bool = True,
    scraper_rate_limits: dict | None = None,
):
    """Lightweight Settings stand-in. SQLModel construction inside tests
    avoids the FastAPI app + db boot path."""
    return SimpleNamespace(
        user_id=user_id,
        sources_enabled=sources_enabled or {},
        consecutive_scrape_failures=consecutive_scrape_failures or {},
        workday_companies=workday_companies or [],
        linkedin_keywords=linkedin_keywords,
        linkedin_location=linkedin_location,
        indeed_keywords=indeed_keywords,
        indeed_location=indeed_location,
        notify_on_errors=notify_on_errors,
        notify_threshold=0.8,
        notifications_enabled={},
        llm_provider=None,
        llm_model="m",
        llm_fallback_provider=None,
        scraper_rate_limits=scraper_rate_limits or {},
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


# ── _compose_query ──────────────────────────────────────────────────────


def test_compose_query_workday_reads_workday_companies():
    s = _make_settings(workday_companies=["foo/External", "bar/Careers"])
    q = scraping._compose_query(JobSource.WORKDAY, s)
    assert q.company_filter == ["foo/External", "bar/Careers"]


def test_compose_query_linkedin_reads_keywords_and_location():
    s = _make_settings(
        linkedin_keywords=["senior swe", "ml engineer"],
        linkedin_location="United States",
    )
    q = scraping._compose_query(JobSource.LINKEDIN, s)
    assert q.keywords == ["senior swe", "ml engineer"]
    assert q.location == "United States"


def test_compose_query_indeed_reads_keywords_and_location():
    s = _make_settings(
        indeed_keywords=["software engineer"],
        indeed_location="Remote",
    )
    q = scraping._compose_query(JobSource.INDEED, s)
    assert q.keywords == ["software engineer"]
    assert q.location == "Remote"


def test_compose_query_greenhouse_reads_env(monkeypatch):
    from config import settings as app_settings

    monkeypatch.setattr(app_settings, "greenhouse_companies", ["anthropic", "openai"])
    s = _make_settings()
    q = scraping._compose_query(JobSource.GREENHOUSE, s)
    assert q.company_filter == ["anthropic", "openai"]


def test_compose_query_lever_reads_env(monkeypatch):
    from config import settings as app_settings

    monkeypatch.setattr(app_settings, "lever_companies", ["replit", "scale"])
    s = _make_settings()
    q = scraping._compose_query(JobSource.LEVER, s)
    assert q.company_filter == ["replit", "scale"]


def test_compose_query_ashby_reads_env(monkeypatch):
    from config import settings as app_settings

    monkeypatch.setattr(app_settings, "ashby_companies", ["linear", "vercel"])
    s = _make_settings()
    q = scraping._compose_query(JobSource.ASHBY, s)
    assert q.company_filter == ["linear", "vercel"]


def test_compose_query_workday_empty_workday_companies():
    s = _make_settings(workday_companies=None)
    q = scraping._compose_query(JobSource.WORKDAY, s)
    assert q.company_filter == []


# ── _scrape_one_user — sources_enabled gating ────────────────────────


@pytest.mark.asyncio
async def test_sources_enabled_false_skips(monkeypatch):
    called = {"n": 0}

    async def fake_run_scraper(*a, **kw):
        called["n"] += 1

    monkeypatch.setattr(scraping, "run_scraper", fake_run_scraper)
    s = _make_settings(sources_enabled={"linkedin": False})
    session = _FakeSession()
    await scraping._scrape_one_user(session, settings=s, source=JobSource.LINKEDIN)
    assert called["n"] == 0


@pytest.mark.asyncio
async def test_sources_enabled_default_true_proceeds(monkeypatch):
    """Missing key in sources_enabled → scrape proceeds."""
    called = {"n": 0}

    async def fake_run_scraper(session, *, scraper, user_id, query, triggered_by):
        called["n"] += 1
        return SimpleNamespace(status=JobScrapeStatus.SUCCESS)

    monkeypatch.setattr(scraping, "run_scraper", fake_run_scraper)
    monkeypatch.setattr(scraping, "llm_get_provider", lambda _s: None)
    s = _make_settings()
    session = _FakeSession()
    await scraping._scrape_one_user(session, settings=s, source=JobSource.LINKEDIN)
    assert called["n"] == 1


# ── _scrape_one_user — provider=None graceful degradation ──────────


@pytest.mark.asyncio
async def test_provider_unavailable_falls_back_to_none(monkeypatch):
    captured = {}

    async def fake_run_scraper(session, *, scraper, user_id, query, triggered_by):
        captured["provider"] = scraper._provider
        return SimpleNamespace(status=JobScrapeStatus.SUCCESS)

    def raise_provider_err(_s):
        raise LLMProviderError("no key", kind="auth_required")

    monkeypatch.setattr(scraping, "run_scraper", fake_run_scraper)
    monkeypatch.setattr(scraping, "llm_get_provider", raise_provider_err)
    s = _make_settings()
    session = _FakeSession()
    await scraping._scrape_one_user(session, settings=s, source=JobSource.LINKEDIN)
    assert captured["provider"] is None


# ── _scrape_one_user — consecutive-FAIL counter ────────────────────


@pytest.mark.asyncio
async def test_failed_run_increments_counter(monkeypatch):
    async def fake_run_scraper(session, *, scraper, user_id, query, triggered_by):
        return SimpleNamespace(status=JobScrapeStatus.FAILED)

    monkeypatch.setattr(scraping, "run_scraper", fake_run_scraper)
    monkeypatch.setattr(scraping, "llm_get_provider", lambda _s: None)
    s = _make_settings()
    session = _FakeSession()
    await scraping._scrape_one_user(session, settings=s, source=JobSource.LINKEDIN)
    assert s.consecutive_scrape_failures["linkedin"] == 1


@pytest.mark.asyncio
async def test_success_resets_counter(monkeypatch):
    async def fake_run_scraper(session, *, scraper, user_id, query, triggered_by):
        return SimpleNamespace(status=JobScrapeStatus.SUCCESS)

    monkeypatch.setattr(scraping, "run_scraper", fake_run_scraper)
    monkeypatch.setattr(scraping, "llm_get_provider", lambda _s: None)
    s = _make_settings(consecutive_scrape_failures={"linkedin": 2})
    session = _FakeSession()
    await scraping._scrape_one_user(session, settings=s, source=JobSource.LINKEDIN)
    assert s.consecutive_scrape_failures["linkedin"] == 0


@pytest.mark.asyncio
async def test_partial_also_resets_counter(monkeypatch):
    async def fake_run_scraper(session, *, scraper, user_id, query, triggered_by):
        return SimpleNamespace(status=JobScrapeStatus.PARTIAL)

    monkeypatch.setattr(scraping, "run_scraper", fake_run_scraper)
    monkeypatch.setattr(scraping, "llm_get_provider", lambda _s: None)
    s = _make_settings(consecutive_scrape_failures={"linkedin": 1})
    session = _FakeSession()
    await scraping._scrape_one_user(session, settings=s, source=JobSource.LINKEDIN)
    assert s.consecutive_scrape_failures["linkedin"] == 0


@pytest.mark.asyncio
async def test_counter_at_or_above_threshold_still_runs_scrape(monkeypatch):
    """Hacker REQUEST_CHANGES fix: counter at threshold MUST NOT block the scrape.

    Pre-fix the cron skipped run_scraper once counter >= 3, which is a
    deadlock — the counter could only be cleared by a SUCCESS, but
    SUCCESS could only happen if run_scraper actually ran.
    """
    called = {"scrape": 0, "alert": 0}

    async def fake_run_scraper(session, *, scraper, user_id, query, triggered_by):
        called["scrape"] += 1
        return SimpleNamespace(status=JobScrapeStatus.SUCCESS)

    async def fake_alert(*, settings, message, http_client=None):
        called["alert"] += 1

    monkeypatch.setattr(scraping, "run_scraper", fake_run_scraper)
    monkeypatch.setattr(scraping, "notify_admin_error", fake_alert)
    monkeypatch.setattr(scraping, "llm_get_provider", lambda _s: None)

    # Counter pinned past-threshold — scrape MUST still run + SUCCESS resets.
    s = _make_settings(consecutive_scrape_failures={"linkedin": 5})
    session = _FakeSession()
    await scraping._scrape_one_user(session, settings=s, source=JobSource.LINKEDIN)
    assert called["scrape"] == 1
    assert called["alert"] == 0
    assert s.consecutive_scrape_failures["linkedin"] == 0


@pytest.mark.asyncio
async def test_threshold_cross_fires_one_alert(monkeypatch):
    """Counter transition 2 → 3 fires exactly one notify_admin_error."""
    called = {"alert": 0, "messages": []}

    async def fake_run_scraper(session, *, scraper, user_id, query, triggered_by):
        return SimpleNamespace(status=JobScrapeStatus.FAILED)

    async def fake_alert(*, settings, message, http_client=None):
        called["alert"] += 1
        called["messages"].append(message)

    monkeypatch.setattr(scraping, "run_scraper", fake_run_scraper)
    monkeypatch.setattr(scraping, "notify_admin_error", fake_alert)
    monkeypatch.setattr(scraping, "llm_get_provider", lambda _s: None)

    s = _make_settings(consecutive_scrape_failures={"linkedin": 2})
    session = _FakeSession()
    await scraping._scrape_one_user(session, settings=s, source=JobSource.LINKEDIN)
    assert s.consecutive_scrape_failures["linkedin"] == 3
    assert called["alert"] == 1
    assert "3x consecutively" in called["messages"][0]


@pytest.mark.asyncio
async def test_past_threshold_failed_run_does_not_re_alert(monkeypatch):
    """Counter already past threshold — another FAILED firing does NOT re-alert.

    Storm guard: hacker MEDIUM finding was "48 alerts/day/user". After
    threshold-cross fires once, subsequent FAILED firings stay silent
    until a SUCCESS / PARTIAL clears the counter.
    """
    called = {"alert": 0}

    async def fake_run_scraper(session, *, scraper, user_id, query, triggered_by):
        return SimpleNamespace(status=JobScrapeStatus.FAILED)

    async def fake_alert(*, settings, message, http_client=None):
        called["alert"] += 1

    monkeypatch.setattr(scraping, "run_scraper", fake_run_scraper)
    monkeypatch.setattr(scraping, "notify_admin_error", fake_alert)
    monkeypatch.setattr(scraping, "llm_get_provider", lambda _s: None)

    s = _make_settings(consecutive_scrape_failures={"linkedin": 4})
    session = _FakeSession()
    await scraping._scrape_one_user(session, settings=s, source=JobSource.LINKEDIN)
    assert s.consecutive_scrape_failures["linkedin"] == 5
    assert called["alert"] == 0


@pytest.mark.asyncio
async def test_first_failed_below_threshold_silent(monkeypatch):
    """Counter 0 → 1: silent. Only the threshold-cross firing alerts."""
    called = {"alert": 0}

    async def fake_run_scraper(session, *, scraper, user_id, query, triggered_by):
        return SimpleNamespace(status=JobScrapeStatus.FAILED)

    async def fake_alert(*, settings, message, http_client=None):
        called["alert"] += 1

    monkeypatch.setattr(scraping, "run_scraper", fake_run_scraper)
    monkeypatch.setattr(scraping, "notify_admin_error", fake_alert)
    monkeypatch.setattr(scraping, "llm_get_provider", lambda _s: None)

    s = _make_settings()
    session = _FakeSession()
    await scraping._scrape_one_user(session, settings=s, source=JobSource.LINKEDIN)
    assert s.consecutive_scrape_failures["linkedin"] == 1
    assert called["alert"] == 0


@pytest.mark.asyncio
async def test_threshold_cross_alert_re_arms_after_success(monkeypatch):
    """After SUCCESS clears the counter, the NEXT threshold-cross fires again."""
    alert_count = {"n": 0}
    next_status: list[JobScrapeStatus] = [
        JobScrapeStatus.FAILED,  # 0 -> 1
        JobScrapeStatus.FAILED,  # 1 -> 2
        JobScrapeStatus.FAILED,  # 2 -> 3 (alert)
        JobScrapeStatus.FAILED,  # 3 -> 4 (silent)
        JobScrapeStatus.SUCCESS,  # reset -> 0
        JobScrapeStatus.FAILED,  # 0 -> 1
        JobScrapeStatus.FAILED,  # 1 -> 2
        JobScrapeStatus.FAILED,  # 2 -> 3 (alert again)
    ]

    async def fake_run_scraper(session, *, scraper, user_id, query, triggered_by):
        return SimpleNamespace(status=next_status.pop(0))

    async def fake_alert(*, settings, message, http_client=None):
        alert_count["n"] += 1

    monkeypatch.setattr(scraping, "run_scraper", fake_run_scraper)
    monkeypatch.setattr(scraping, "notify_admin_error", fake_alert)
    monkeypatch.setattr(scraping, "llm_get_provider", lambda _s: None)

    s = _make_settings()
    session = _FakeSession()
    for _ in range(8):
        await scraping._scrape_one_user(session, settings=s, source=JobSource.LINKEDIN)
    assert alert_count["n"] == 2
    assert s.consecutive_scrape_failures["linkedin"] == 3


# ── _scrape_one_user — failure isolation per user ──────────────────


@pytest.mark.asyncio
async def test_top_level_exception_does_not_propagate(monkeypatch):
    """run_scraper raising — _scrape_one_user catches + logs + alerts + bumps."""
    alert = {"count": 0, "msg": None}

    async def boom(*a, **kw):
        raise RuntimeError("database unreachable")

    async def fake_alert(*, settings, message, http_client=None):
        alert["count"] += 1
        alert["msg"] = message

    monkeypatch.setattr(scraping, "run_scraper", boom)
    monkeypatch.setattr(scraping, "notify_admin_error", fake_alert)
    monkeypatch.setattr(scraping, "llm_get_provider", lambda _s: None)

    s = _make_settings()
    session = _FakeSession()
    # Must not raise.
    await scraping._scrape_one_user(session, settings=s, source=JobSource.LINKEDIN)
    assert s.consecutive_scrape_failures["linkedin"] == 1
    # Hacker LOW finding: broad-except path now signals the operator.
    assert alert["count"] == 1
    assert "raised at top level" in alert["msg"]
    assert "database unreachable" in alert["msg"]


# ── register_scraping_jobs ──────────────────────────────────────────


def test_register_scraping_jobs_count_matches_registry():
    scheduler = AsyncIOScheduler(timezone="UTC")
    scraping.register_scraping_jobs(scheduler)
    job_ids = {j.id for j in scheduler.get_jobs()}
    expected = {f"scraping.{src}" for src in scraping.scraper_registry}
    assert job_ids == expected


@pytest.mark.asyncio
async def test_register_scraping_jobs_idempotent():
    """Re-registration with `replace_existing=True` must not duplicate jobs.

    The scheduler is started in paused mode so jobs flush from `_pending_jobs`
    into the jobstore — `replace_existing` only consults the jobstore, not
    the pending queue. AsyncIOScheduler needs a running event loop to start.
    """
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.start(paused=True)
    try:
        scraping.register_scraping_jobs(scheduler)
        scraping.register_scraping_jobs(scheduler)
        job_ids = [j.id for j in scheduler.get_jobs()]
    finally:
        scheduler.shutdown(wait=False)
    assert len(job_ids) == len(set(job_ids))
    assert len(job_ids) == len(scraping.scraper_registry)


def test_register_scraping_jobs_indeed_uses_interval_trigger():
    """Cron doesn't support 90-min steps — Indeed must use IntervalTrigger."""
    scheduler = AsyncIOScheduler(timezone="UTC")
    scraping.register_scraping_jobs(scheduler)
    indeed_job = scheduler.get_job("scraping.indeed")
    assert indeed_job is not None
    assert isinstance(indeed_job.trigger, IntervalTrigger)
    assert indeed_job.trigger.interval.total_seconds() == 90 * 60


def test_register_scraping_jobs_non_indeed_use_cron_trigger():
    scheduler = AsyncIOScheduler(timezone="UTC")
    scraping.register_scraping_jobs(scheduler)
    for source_value in scraping.scraper_registry:
        if source_value == JobSource.INDEED.value:
            continue
        job = scheduler.get_job(f"scraping.{source_value}")
        assert isinstance(job.trigger, CronTrigger), f"{source_value} not a CronTrigger"


def test_register_scraping_jobs_all_have_jitter_30():
    scheduler = AsyncIOScheduler(timezone="UTC")
    scraping.register_scraping_jobs(scheduler)
    for source_value in scraping.scraper_registry:
        job = scheduler.get_job(f"scraping.{source_value}")
        assert job.trigger.jitter == 30, f"{source_value} missing jitter=30"


def test_register_scraping_jobs_misfire_grace_time_300():
    scheduler = AsyncIOScheduler(timezone="UTC")
    scraping.register_scraping_jobs(scheduler)
    for source_value in scraping.scraper_registry:
        job = scheduler.get_job(f"scraping.{source_value}")
        assert job.misfire_grace_time == 300


def test_register_scraping_jobs_max_instances_one():
    scheduler = AsyncIOScheduler(timezone="UTC")
    scraping.register_scraping_jobs(scheduler)
    for source_value in scraping.scraper_registry:
        job = scheduler.get_job(f"scraping.{source_value}")
        assert job.max_instances == 1


def test_default_cron_schedules_cover_all_non_indeed_sources():
    """Every cron-driven source (i.e. not Indeed) has a default schedule."""
    for source_value in scraping.scraper_registry:
        if source_value == JobSource.INDEED.value:
            continue
        assert source_value in scraping._DEFAULT_CRON_SCHEDULES


def test_register_all_includes_scraping_jobs():
    """`jobs.register_all` registers the 5 admin/auto-apply + 6 scraping jobs."""
    from scheduler.jobs import register_all

    scheduler = AsyncIOScheduler(timezone="UTC")
    register_all(scheduler)
    job_ids = {j.id for j in scheduler.get_jobs()}
    # 5 admin/auto-apply jobs + 6 scraping jobs.
    for admin_id in (
        "applications.auto_apply",
        "admin.aggregate_costs",
        "admin.cleanup_stale_docs",
        "admin.daily_db_snapshot",
        "admin.refresh_oauth_tokens",
    ):
        assert admin_id in job_ids
    for source_value in scraping.scraper_registry:
        assert f"scraping.{source_value}" in job_ids


# ── _scrape_source iterates all Settings rows ──────────────────────


class _NoopScraper(ScraperBase):
    source = JobSource.MANUAL
    board = ApplicationBoard.MANUAL

    async def scrape(self, query: ScrapeQuery) -> AsyncIterator[RawJob]:
        if False:  # pragma: no cover
            yield  # type: ignore[unreachable]


# ── Plan 38 § D.1 — operator overrides flow into Crawl4AIClient ─────────


@pytest.mark.asyncio
async def test_scrape_one_user_uses_operator_override_for_rate_limit(monkeypatch):
    """Settings.scraper_rate_limits override > class-attr fallback."""
    captured = {}

    async def fake_run_scraper(session, *, scraper, user_id, query, triggered_by):
        captured["rpm"] = scraper._client._rate_limit_per_minute
        captured["delays"] = scraper._client._random_delay_seconds
        return SimpleNamespace(status=JobScrapeStatus.SUCCESS)

    monkeypatch.setattr(scraping, "run_scraper", fake_run_scraper)
    monkeypatch.setattr(scraping, "llm_get_provider", lambda _s: None)

    s = _make_settings(
        scraper_rate_limits={
            "linkedin": {"rpm": 1.5, "delay_lo": 2.0, "delay_hi": 4.0},
        }
    )
    session = _FakeSession()
    await scraping._scrape_one_user(session, settings=s, source=JobSource.LINKEDIN)

    assert captured["rpm"] == 1.5
    assert captured["delays"] == (2.0, 4.0)


@pytest.mark.asyncio
async def test_scrape_one_user_falls_back_when_no_override(monkeypatch):
    """No `scraper_rate_limits` entry → class-attr fallback (LinkedIn: 0.4 rpm)."""
    captured = {}

    async def fake_run_scraper(session, *, scraper, user_id, query, triggered_by):
        captured["rpm"] = scraper._client._rate_limit_per_minute
        return SimpleNamespace(status=JobScrapeStatus.SUCCESS)

    monkeypatch.setattr(scraping, "run_scraper", fake_run_scraper)
    monkeypatch.setattr(scraping, "llm_get_provider", lambda _s: None)

    s = _make_settings()  # scraper_rate_limits={} by default.
    session = _FakeSession()
    await scraping._scrape_one_user(session, settings=s, source=JobSource.LINKEDIN)

    # Class-attr fallback per `_CLASS_ATTR_FALLBACK[LINKEDIN]`.
    assert captured["rpm"] == 0.4


@pytest.mark.asyncio
async def test_scrape_one_user_threads_undetected_adapter_class_attr(monkeypatch):
    """`scraper_cls.use_undetected_adapter` threads into the Crawl4AIClient."""
    captured = {}

    async def fake_run_scraper(session, *, scraper, user_id, query, triggered_by):
        captured["undetected"] = scraper._client._use_undetected_adapter
        return SimpleNamespace(status=JobScrapeStatus.SUCCESS)

    monkeypatch.setattr(scraping, "run_scraper", fake_run_scraper)
    monkeypatch.setattr(scraping, "llm_get_provider", lambda _s: None)

    # IndeedScraper.use_undetected_adapter inherits default False.
    s = _make_settings()
    session = _FakeSession()
    await scraping._scrape_one_user(session, settings=s, source=JobSource.INDEED)

    assert captured["undetected"] is False


@pytest.mark.asyncio
async def test_scrape_source_iterates_all_settings_rows(monkeypatch):
    """One scrape_source firing → _scrape_one_user called for every Settings."""

    calls = []

    async def fake_one_user(session, *, settings, source):
        calls.append(settings.user_id)

    monkeypatch.setattr(scraping, "_scrape_one_user", fake_one_user)

    a = _make_settings(user_id=1)
    b = _make_settings(user_id=2)

    class _RowsSession(_FakeSession):
        async def exec(self, _stmt):
            return SimpleNamespace(one_or_none=lambda: None, all=lambda: [a, b], one=lambda: 0)

    # Patch async_session to return our pre-loaded session.
    class _CM:
        async def __aenter__(self_):
            self_.session = _RowsSession()
            return self_.session

        async def __aexit__(self_, exc_type, exc, tb):
            pass

    monkeypatch.setattr(scraping, "async_session", lambda: _CM())

    await scraping._scrape_source(JobSource.LINKEDIN)
    assert calls == [1, 2]
