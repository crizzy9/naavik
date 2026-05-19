"""Site registry tests — plan 33 § D.7 / D.8 (2 tests)."""

from __future__ import annotations

from models import JobSource
from scraper.sites import (
    AshbyScraper,
    GreenhouseScraper,
    IndeedScraper,
    LeverScraper,
    LinkedInScraper,
    SampleScraper,
    WorkdayScraper,
    scrapers,
)


def test_scrapers_registry_has_six_sources():
    """`scrapers` is keyed by `JobSource.value` and contains exactly the six
    production sources from plan 33 § D.7."""
    assert set(scrapers.keys()) == {
        JobSource.LINKEDIN.value,
        JobSource.WORKDAY.value,
        JobSource.GREENHOUSE.value,
        JobSource.LEVER.value,
        JobSource.ASHBY.value,
        JobSource.INDEED.value,
    }
    assert len(scrapers) == 6
    assert scrapers[JobSource.LINKEDIN.value] is LinkedInScraper
    assert scrapers[JobSource.WORKDAY.value] is WorkdayScraper
    assert scrapers[JobSource.GREENHOUSE.value] is GreenhouseScraper
    assert scrapers[JobSource.LEVER.value] is LeverScraper
    assert scrapers[JobSource.ASHBY.value] is AshbyScraper
    assert scrapers[JobSource.INDEED.value] is IndeedScraper


def test_sample_scraper_not_in_registry():
    """SampleScraper is exported for test reuse but NEVER dispatch-registered."""
    assert SampleScraper not in scrapers.values()
    assert JobSource.MANUAL.value not in scrapers
