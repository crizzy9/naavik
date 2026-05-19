"""SampleScraper tests — plan 29 § D.8 / D.9.

Materializes the 3-RawJob stream + asserts field shape. SampleScraper does
not touch the network, so no Crawl4AI mock is needed (default client is
constructed but never called).
"""

from __future__ import annotations

import pytest

from models import (
    ApplicationBoard,
    JobSource,
    RemotePolicy,
    SeniorityLevel,
)
from scraper.crawl4ai_client import Crawl4AIClient
from scraper.sites.sample import SampleScraper
from scraper.types import ScrapeQuery


@pytest.mark.asyncio
async def test_sample_scraper_yields_three_rawjobs():
    """The fixture promise: exactly 3 RawJobs."""
    scraper = SampleScraper(client=Crawl4AIClient(random_delay_seconds=(0.0, 0.0)))
    rawjobs = [job async for job in scraper.scrape(ScrapeQuery())]

    assert len(rawjobs) == 3
    assert all(j.source is JobSource.MANUAL for j in rawjobs)
    assert all(j.board is ApplicationBoard.MANUAL for j in rawjobs)


@pytest.mark.asyncio
async def test_sample_scraper_emits_expected_external_ids():
    scraper = SampleScraper(client=Crawl4AIClient(random_delay_seconds=(0.0, 0.0)))
    rawjobs = [job async for job in scraper.scrape(ScrapeQuery())]

    assert [j.external_id for j in rawjobs] == [
        "manual-sample-001",
        "manual-sample-002",
        "manual-sample-003",
    ]


@pytest.mark.asyncio
async def test_sample_scraper_emits_distinct_hint_shapes():
    """Each of the 3 RawJobs exercises a different RemotePolicy + SeniorityLevel."""
    scraper = SampleScraper(client=Crawl4AIClient(random_delay_seconds=(0.0, 0.0)))
    rawjobs = [job async for job in scraper.scrape(ScrapeQuery())]

    remotes = [j.remote_policy_hint for j in rawjobs]
    seniorities = [j.seniority_level_hint for j in rawjobs]

    assert remotes == [RemotePolicy.REMOTE, RemotePolicy.HYBRID, RemotePolicy.ONSITE]
    assert seniorities == [SeniorityLevel.SENIOR, SeniorityLevel.STAFF, SeniorityLevel.PRINCIPAL]


def test_sample_scraper_not_registered_for_production_dispatch():
    """SampleScraper is a test fixture; production registry stays empty."""
    from scraper.sites import scrapers

    # SampleScraper class itself is exported, but the production lookup dict
    # is empty until 0.2.0.07 adds the real source scrapers.
    assert scrapers == {}
