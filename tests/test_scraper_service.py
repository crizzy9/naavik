"""scraper_service.run_scraper tests — plan 29 § D.9 + § D.10.

Exercises the `JobScrapeRun` lifecycle (RUNNING -> SUCCESS / PARTIAL / FAILED /
TIMED_OUT) via an in-memory fake session (mirrors `tests/test_job_service.py`)
+ a SampleScraper variant. Each test verifies status derivation + counter
math without touching Postgres.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from models import (
    ApplicationBoard,
    JobScrapeStatus,
    JobSource,
)
from scraper.base import ScraperBase
from scraper.crawl4ai_client import Crawl4AIClient
from scraper.sites.sample import SampleScraper
from scraper.types import RawJob, ScrapeQuery
from services import scraper_service

pytestmark = pytest.mark.uses_sample_data_shims

# ── In-memory fakes ──────────────────────────────────────────────────────


class _FakeSession:
    """Mirror of tests/test_job_service.py:_FakeSession; tracks add()/flush()
    and serves queued canned exec() results.

    Exposes a sqlite-flavored `bind.dialect` so the tier-3 dedup query
    (plan 34) picks the LIKE fallback branch.
    """

    def __init__(self) -> None:
        self.added: list = []
        self.exec_queue: list = []
        self.flush_count = 0
        self.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flush_count += 1

    async def exec(self, _stmt):
        if not self.exec_queue:
            return SimpleNamespace(one_or_none=lambda: None, all=lambda: [], one=lambda: 0)
        return self.exec_queue.pop(0)


def _exec_one(value):
    return SimpleNamespace(one_or_none=lambda: value, all=lambda: [value] if value else [])


def _exec_all_empty():
    """Sentinel result for the tier-3 dedup candidate query — no matches."""
    return SimpleNamespace(one_or_none=lambda: None, all=lambda: [], one=lambda: 0)


# ── Helpers ──────────────────────────────────────────────────────────────


def _client_no_sleep() -> Crawl4AIClient:
    return Crawl4AIClient(random_delay_seconds=(0.0, 0.0), rate_limit_per_minute=1_000_000)


class _SingleJobScraper(ScraperBase):
    """Yields exactly one RawJob (the supplied instance) then completes."""

    source = JobSource.MANUAL
    board = ApplicationBoard.MANUAL

    def __init__(self, raw_job: RawJob) -> None:
        super().__init__(client=_client_no_sleep())
        self._raw_job = raw_job

    async def scrape(self, query: ScrapeQuery) -> AsyncIterator[RawJob]:
        yield self._raw_job


class _RaisingScraper(ScraperBase):
    """Yields `yield_before` RawJobs, then raises `exc`."""

    source = JobSource.MANUAL
    board = ApplicationBoard.MANUAL

    def __init__(self, *, yield_before: int, exc: BaseException) -> None:
        super().__init__(client=_client_no_sleep())
        self._yield_before = yield_before
        self._exc = exc

    async def scrape(self, query: ScrapeQuery) -> AsyncIterator[RawJob]:
        for i in range(self._yield_before):
            yield RawJob(
                source=JobSource.MANUAL,
                external_id=f"manual-raise-{i:03d}",
                source_url=f"https://example.com/jobs/raise/{i}",
                board=ApplicationBoard.MANUAL,
                company_name="Acme",
                position_title="Engineer",
            )
        raise self._exc


def _setup_session_for_sample(scraper: SampleScraper, *, all_new: bool = True) -> _FakeSession:
    """Wire a fake session whose exec() returns None for each upsert's
    existence check — so every upsert creates a new row.

    Cold-cache upserts (tier-1 miss) issue a SECOND exec for tier-3 dedup
    candidate lookup (plan 34 / 0.2.0.09); we queue an empty `_exec_all`
    after each tier-1 None to keep the candidate filter benign.
    """
    session = _FakeSession()
    n_yields = 3
    if all_new:
        for _ in range(n_yields):
            session.exec_queue.append(_exec_one(None))
            session.exec_queue.append(_exec_all_empty())
    else:
        # alternating new / existing — used to test the updated_jobs counter.
        for i in range(n_yields):
            if i % 2 == 0:
                session.exec_queue.append(_exec_one(None))
                session.exec_queue.append(_exec_all_empty())
            else:
                session.exec_queue.append(
                    _exec_one(
                        SimpleNamespace(
                            id=10 + i,
                            user_id=1,
                            source=JobSource.MANUAL,
                            external_id=f"manual-sample-{i:03d}",
                            description_extracted_at=None,
                            updated_at=None,
                            raw_meta={},
                            last_scrape_run_id=None,
                        )
                    )
                )
    return session


# ── SUCCESS: clean stream, all jobs new ──────────────────────────────────


@pytest.mark.asyncio
async def test_run_scraper_success_three_new_jobs():
    """SampleScraper yields 3; every upsert creates → status=SUCCESS."""
    scraper = SampleScraper(client=_client_no_sleep())
    session = _setup_session_for_sample(scraper, all_new=True)

    run = await scraper_service.run_scraper(
        session,  # type: ignore[arg-type]
        scraper=scraper,
        user_id=1,
        triggered_by="test",
    )

    assert run.status is JobScrapeStatus.SUCCESS
    assert run.listings_returned == 3
    assert run.new_jobs == 3
    assert run.updated_jobs == 0
    assert run.errors == []
    assert run.finished_at is not None
    assert run.duration_ms is not None and run.duration_ms >= 0
    assert run.raw_meta["scraper_name"] == "SampleScraper"


# ── SUCCESS: mixed new + existing ────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_scraper_success_mixed_new_and_existing():
    """Pattern: new / existing / new → 2 new, 1 updated."""
    scraper = SampleScraper(client=_client_no_sleep())
    session = _setup_session_for_sample(scraper, all_new=False)

    run = await scraper_service.run_scraper(
        session,  # type: ignore[arg-type]
        scraper=scraper,
        user_id=1,
    )

    assert run.status is JobScrapeStatus.SUCCESS
    assert run.listings_returned == 3
    assert run.new_jobs == 2
    assert run.updated_jobs == 1


# ── FAILED: top-level exception before any RawJob is yielded ─────────────


@pytest.mark.asyncio
async def test_run_scraper_failed_when_scraper_raises_before_any_yield():
    """Tier-2 fatal before first yield → status=FAILED + errors[] captures."""
    scraper = _RaisingScraper(yield_before=0, exc=RuntimeError("auth invalid"))
    session = _FakeSession()

    run = await scraper_service.run_scraper(
        session,  # type: ignore[arg-type]
        scraper=scraper,
        user_id=1,
    )

    assert run.status is JobScrapeStatus.FAILED
    assert run.listings_returned == 0
    assert run.new_jobs == 0
    assert any("kind=fatal" in e for e in run.errors)
    assert any("RuntimeError" in e for e in run.errors)


# ── PARTIAL: top-level exception after some yields ───────────────────────


@pytest.mark.asyncio
async def test_run_scraper_partial_when_scraper_raises_after_some_yields():
    """Yield 2, then raise → status=PARTIAL with 2 jobs landed."""
    scraper = _RaisingScraper(yield_before=2, exc=RuntimeError("network blip"))
    session = _FakeSession()
    # 2 upsert existence checks return None → 2 new jobs land before raise.
    # Each cold-cache upsert also issues a tier-3 dedup candidate query
    # (plan 34) which we satisfy with empty `_exec_all` results.
    session.exec_queue = [
        _exec_one(None),
        _exec_all_empty(),
        _exec_one(None),
        _exec_all_empty(),
    ]

    run = await scraper_service.run_scraper(
        session,  # type: ignore[arg-type]
        scraper=scraper,
        user_id=1,
    )

    assert run.status is JobScrapeStatus.PARTIAL
    assert run.listings_returned == 2
    assert run.new_jobs == 2
    assert any("kind=fatal" in e for e in run.errors)


# ── TIMED_OUT: CancelledError ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_scraper_timed_out_on_cancelled_error():
    """asyncio.CancelledError → status=TIMED_OUT; re-raised to caller."""
    scraper = _RaisingScraper(yield_before=0, exc=asyncio.CancelledError())
    session = _FakeSession()

    with pytest.raises(asyncio.CancelledError):
        await scraper_service.run_scraper(
            session,  # type: ignore[arg-type]
            scraper=scraper,
            user_id=1,
        )

    # JobScrapeRun.status set to TIMED_OUT in `finally` before re-raise; the
    # run row should appear in session.added (the record_scrape_run insert
    # path) and have its mutated status visible via session.added inspection.
    runs = [obj for obj in session.added if hasattr(obj, "status")]
    assert runs, "record_scrape_run should have added the JobScrapeRun"
    assert runs[0].status is JobScrapeStatus.TIMED_OUT
    assert any("kind=cancelled" in e for e in runs[0].errors)


# ── PARTIAL: per-listing upsert failure inherits to errors[] ─────────────


@pytest.mark.asyncio
async def test_run_scraper_per_listing_upsert_failure_becomes_partial():
    """Upsert raises mid-stream → error appended; status=PARTIAL afterward."""
    scraper = SampleScraper(client=_client_no_sleep())
    session = _FakeSession()

    # Return values for the 3 upsert existence checks: first 2 succeed (None);
    # third triggers a write-side exception via a side-effect monkey-patch.
    # Each tier-1 None pairs with an empty tier-3 dedup candidate result.
    session.exec_queue = [
        _exec_one(None),
        _exec_all_empty(),
        _exec_one(None),
        _exec_all_empty(),
        _exec_one(None),
        _exec_all_empty(),
    ]

    real_flush = session.flush
    flush_calls = {"n": 0}

    async def flaky_flush() -> None:
        flush_calls["n"] += 1
        # The first flush (record_scrape_run insert) succeeds.
        # Then each upsert calls flush once (1, 2, 3); raise on the 4th call
        # (= the 3rd upsert's flush).
        if flush_calls["n"] == 4:
            raise RuntimeError("integrity error on third upsert")
        await real_flush()

    session.flush = flaky_flush  # type: ignore[assignment]

    run = await scraper_service.run_scraper(
        session,  # type: ignore[arg-type]
        scraper=scraper,
        user_id=1,
    )

    assert run.status is JobScrapeStatus.PARTIAL
    # Listings always increment per yield, regardless of upsert outcome.
    assert run.listings_returned == 3
    # 2 upserts succeeded; 1 raised on flush.
    assert run.new_jobs == 2
    assert any("kind=upsert_failure" in e for e in run.errors)


# ── scraper._errors aggregation ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_scraper_inherits_scraper_internal_errors():
    """Scraper that pre-populates `self._errors` → those propagate to run.errors."""

    class NoisyScraper(SampleScraper):
        async def scrape(self, query: ScrapeQuery) -> AsyncIterator[RawJob]:
            self._errors.append("stage=detail url=x kind=parse_failure msg=bad-html")
            async for j in super().scrape(query):
                yield j

    scraper = NoisyScraper(client=_client_no_sleep())
    session = _setup_session_for_sample(scraper, all_new=True)

    run = await scraper_service.run_scraper(
        session,  # type: ignore[arg-type]
        scraper=scraper,
        user_id=1,
    )

    # 3 yields + 0 upsert failures + 1 scraper-internal error → PARTIAL.
    assert run.status is JobScrapeStatus.PARTIAL
    assert run.listings_returned == 3
    assert run.new_jobs == 3
    assert any("parse_failure" in e for e in run.errors)


# ── Post-finalize notification dispatch (plan 37 / 0.2.0.12) ────────────


@pytest.mark.asyncio
async def test_run_scraper_dispatches_notify_on_success_with_new_jobs():
    """SUCCESS run with new_jobs > 0 → notify_scrape_run_summary fires once."""
    scraper = SampleScraper(client=_client_no_sleep())
    session = _setup_session_for_sample(scraper, all_new=True)
    # Settings lookup (post-finalize) returns a stub for user_id=1.
    fake_settings = SimpleNamespace(user_id=1)
    session.exec_queue.append(_exec_one(fake_settings))
    # list_new_jobs_from_run query returns 2 stand-in jobs.
    session.exec_queue.append(
        SimpleNamespace(
            one_or_none=lambda: None,
            all=lambda: [
                SimpleNamespace(role="A", company="X", url="https://x.example/1"),
                SimpleNamespace(role="B", company="Y", url="https://y.example/2"),
            ],
        )
    )

    notify_mock = AsyncMock()
    with patch("services.scraper_service.notify_scrape_run_summary", new=notify_mock):
        run = await scraper_service.run_scraper(
            session,  # type: ignore[arg-type]
            scraper=scraper,
            user_id=1,
        )

    assert run.status is JobScrapeStatus.SUCCESS
    assert run.new_jobs == 3
    notify_mock.assert_awaited_once()
    kwargs = notify_mock.await_args.kwargs
    assert kwargs["settings"] is fake_settings
    assert kwargs["run"] is run
    assert len(kwargs["top_jobs"]) == 2


@pytest.mark.asyncio
async def test_run_scraper_skips_notify_when_no_new_jobs():
    """All upserts hit existing rows → new_jobs == 0 → no notify."""
    scraper = SampleScraper(client=_client_no_sleep())
    session = _FakeSession()
    # 3 yields, each existence check returns an existing Job row → updated.
    for i in range(3):
        existing = SimpleNamespace(
            id=10 + i,
            user_id=1,
            source=JobSource.MANUAL,
            external_id=f"manual-sample-{i:03d}",
            description_extracted_at=None,
            updated_at=None,
            raw_meta={},
            last_scrape_run_id=None,
        )
        session.exec_queue.append(_exec_one(existing))

    notify_mock = AsyncMock()
    with patch("services.scraper_service.notify_scrape_run_summary", new=notify_mock):
        run = await scraper_service.run_scraper(
            session,  # type: ignore[arg-type]
            scraper=scraper,
            user_id=1,
        )

    assert run.status is JobScrapeStatus.SUCCESS
    assert run.new_jobs == 0
    notify_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_scraper_skips_notify_on_failed_status():
    """FAILED status → no notify even if new_jobs > 0 (status guard)."""
    scraper = _RaisingScraper(yield_before=0, exc=RuntimeError("auth invalid"))
    session = _FakeSession()

    notify_mock = AsyncMock()
    with patch("services.scraper_service.notify_scrape_run_summary", new=notify_mock):
        run = await scraper_service.run_scraper(
            session,  # type: ignore[arg-type]
            scraper=scraper,
            user_id=1,
        )

    assert run.status is JobScrapeStatus.FAILED
    notify_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_scraper_notify_false_skips_dispatch():
    """notify=False opt-out → no notify even on SUCCESS with new_jobs > 0."""
    scraper = SampleScraper(client=_client_no_sleep())
    session = _setup_session_for_sample(scraper, all_new=True)

    notify_mock = AsyncMock()
    with patch("services.scraper_service.notify_scrape_run_summary", new=notify_mock):
        run = await scraper_service.run_scraper(
            session,  # type: ignore[arg-type]
            scraper=scraper,
            user_id=1,
            notify=False,
        )

    assert run.status is JobScrapeStatus.SUCCESS
    assert run.new_jobs == 3
    notify_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_scraper_notify_failure_does_not_block_lifecycle():
    """A raise from notify_scrape_run_summary is swallowed; run still returns."""
    scraper = SampleScraper(client=_client_no_sleep())
    session = _setup_session_for_sample(scraper, all_new=True)
    fake_settings = SimpleNamespace(user_id=1)
    session.exec_queue.append(_exec_one(fake_settings))
    session.exec_queue.append(SimpleNamespace(one_or_none=lambda: None, all=lambda: []))

    async def _boom(**_kw):
        raise RuntimeError("notify died")

    with patch("services.scraper_service.notify_scrape_run_summary", new=_boom):
        run = await scraper_service.run_scraper(
            session,  # type: ignore[arg-type]
            scraper=scraper,
            user_id=1,
        )

    # Run lifecycle stayed SUCCESS; notify failure is best-effort.
    assert run.status is JobScrapeStatus.SUCCESS
    assert run.new_jobs == 3


# ── Plan 38 § D.7 — rate-limit telemetry in JobScrapeRun.raw_meta ────────


@pytest.mark.asyncio
async def test_run_scraper_writes_rate_limit_telemetry_to_raw_meta():
    """Plan 38: rate_limit_hits + backoff_total_s + ua land in raw_meta."""
    scraper = SampleScraper(client=_client_no_sleep())
    session = _setup_session_for_sample(scraper, all_new=True)
    # Simulate the client recorded one 429 during the stream.
    scraper._client.rate_limit_hits = 2
    scraper._client.backoff_total_s = 4.5

    run = await scraper_service.run_scraper(
        session,  # type: ignore[arg-type]
        scraper=scraper,
        user_id=1,
        notify=False,
    )

    assert run.status is JobScrapeStatus.SUCCESS
    rl = run.raw_meta.get("rate_limit")
    assert rl is not None
    assert rl["hits"] == 2
    assert rl["backoff_total_s"] == 4.5
    assert rl["ua"] == scraper._client.user_agent


@pytest.mark.asyncio
async def test_run_scraper_writes_adapter_used_telemetry():
    """`raw_meta['adapter_used']` reflects scraper.use_undetected_adapter."""
    scraper = SampleScraper(client=_client_no_sleep())
    session = _setup_session_for_sample(scraper, all_new=True)

    run = await scraper_service.run_scraper(
        session,  # type: ignore[arg-type]
        scraper=scraper,
        user_id=1,
        notify=False,
    )

    # SampleScraper inherits ScraperBase default (use_undetected_adapter=False).
    assert run.raw_meta.get("adapter_used") == "stealth"


@pytest.mark.asyncio
async def test_run_scraper_adapter_used_telemetry_when_undetected():
    """Class-attr `use_undetected_adapter=True` surfaces as 'undetected' in raw_meta."""

    class _UndetectedSampleScraper(SampleScraper):
        use_undetected_adapter = True

    scraper = _UndetectedSampleScraper(client=_client_no_sleep())
    session = _setup_session_for_sample(scraper, all_new=True)

    run = await scraper_service.run_scraper(
        session,  # type: ignore[arg-type]
        scraper=scraper,
        user_id=1,
        notify=False,
    )

    assert run.raw_meta.get("adapter_used") == "undetected"


@pytest.mark.asyncio
async def test_run_scraper_preserves_existing_raw_meta_keys():
    """Existing raw_meta keys (scraper_name, query) survive the telemetry write."""
    scraper = SampleScraper(client=_client_no_sleep())
    session = _setup_session_for_sample(scraper, all_new=True)

    run = await scraper_service.run_scraper(
        session,  # type: ignore[arg-type]
        scraper=scraper,
        user_id=1,
        notify=False,
    )

    # record_scrape_run set these initially; finally block must not nuke them.
    assert run.raw_meta["scraper_name"] == "SampleScraper"
    assert "query" in run.raw_meta
    # Plan 38 added these.
    assert "rate_limit" in run.raw_meta
    assert "adapter_used" in run.raw_meta


@pytest.mark.asyncio
async def test_run_scraper_telemetry_works_when_failed():
    """FAILED runs still carry telemetry (operator wants RL data for failures)."""
    scraper = _RaisingScraper(yield_before=0, exc=RuntimeError("auth invalid"))
    scraper._client.rate_limit_hits = 1

    session = _FakeSession()
    run = await scraper_service.run_scraper(
        session,  # type: ignore[arg-type]
        scraper=scraper,
        user_id=1,
    )

    assert run.status is JobScrapeStatus.FAILED
    assert run.raw_meta["rate_limit"]["hits"] == 1
    assert run.raw_meta["adapter_used"] == "stealth"
