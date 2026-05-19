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

# ── In-memory fakes ──────────────────────────────────────────────────────


class _FakeSession:
    """Mirror of tests/test_job_service.py:_FakeSession; tracks add()/flush()
    and serves queued canned exec() results."""

    def __init__(self) -> None:
        self.added: list = []
        self.exec_queue: list = []
        self.flush_count = 0

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
    existence check — so every upsert creates a new row."""
    session = _FakeSession()
    # 1 exec() for record_scrape_run (returns nothing meaningful;
    # job_service.record_scrape_run just does add + flush). record_scrape_run
    # does not call session.exec; sample yields 3 jobs so we queue 3 exec()
    # results for the upsert existence-check.
    n_yields = 3
    if all_new:
        for _ in range(n_yields):
            session.exec_queue.append(_exec_one(None))
    else:
        # alternating new / existing — used to test the updated_jobs counter.
        for i in range(n_yields):
            if i % 2 == 0:
                session.exec_queue.append(_exec_one(None))
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
    session.exec_queue = [_exec_one(None), _exec_one(None)]

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
    session.exec_queue = [_exec_one(None), _exec_one(None), _exec_one(None)]

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
