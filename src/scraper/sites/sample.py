"""SampleScraper — test fixture, NOT a production source.

Per plan 29 § D.8 + docs/design/SCRAPER_BASE.md § J. Yields 3 hard-coded
`RawJob` instances so the scraper-substrate contract has something to
exercise. Purpose:

- Smoke test the ABC contract (`tests/test_scraper_base.py`).
- Smoke test the service-layer lifecycle (`tests/test_scraper_service.py`).
- Manual smoke for engineers (instantiate + materialize the async generator).

This scraper is NOT registered in `sites/__init__.py:scrapers` for
production dispatch. It does NOT appear in any APScheduler cron job. If a
future plan needs a "manual seed-job upload" scraper, add a new
`ManualUploadScraper` subclass — do NOT reuse `SampleScraper`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from models import (
    ApplicationBoard,
    JobSource,
    RemotePolicy,
    SeniorityLevel,
    VisaRestriction,
)

from ..base import ScraperBase
from ..types import RawJob, ScrapeQuery


class SampleScraper(ScraperBase):
    """Three hard-coded RawJobs for contract + service-layer smoke tests."""

    source = JobSource.MANUAL
    board = ApplicationBoard.MANUAL

    async def scrape(self, query: ScrapeQuery) -> AsyncIterator[RawJob]:
        yield RawJob(
            source=JobSource.MANUAL,
            external_id="manual-sample-001",
            source_url="https://example.com/jobs/001",
            board=ApplicationBoard.MANUAL,
            url_type="manual",
            company_name="Acme Robotics",
            position_title="Senior Platform Engineer",
            location_raw="Remote — US",
            description_text="Build distributed systems for industrial robots.",
            remote_policy_hint=RemotePolicy.REMOTE,
            seniority_level_hint=SeniorityLevel.SENIOR,
            visa_restriction_hint=VisaRestriction.SPONSORSHIP_AVAILABLE,
            raw_meta={"sample_idx": 1},
        )
        yield RawJob(
            source=JobSource.MANUAL,
            external_id="manual-sample-002",
            source_url="https://example.com/jobs/002",
            board=ApplicationBoard.MANUAL,
            url_type="manual",
            company_name="Helios Labs",
            position_title="Staff Software Engineer, ML Infra",
            location_raw="San Francisco, CA (hybrid)",
            description_text="Train large foundation models on internal hardware.",
            remote_policy_hint=RemotePolicy.HYBRID,
            seniority_level_hint=SeniorityLevel.STAFF,
            raw_meta={"sample_idx": 2},
        )
        yield RawJob(
            source=JobSource.MANUAL,
            external_id="manual-sample-003",
            source_url="https://example.com/jobs/003",
            board=ApplicationBoard.MANUAL,
            url_type="manual",
            company_name="Polar Compute",
            position_title="Principal Engineer, Distributed Systems",
            location_raw="New York, NY",
            description_text="Lead architecture for a multi-region database.",
            remote_policy_hint=RemotePolicy.ONSITE,
            seniority_level_hint=SeniorityLevel.PRINCIPAL,
            raw_meta={"sample_idx": 3},
        )
