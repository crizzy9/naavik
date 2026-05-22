"""ScraperBase ABC contract tests — plan 29 § D.1 / D.9.

Verifies abstract-method enforcement and class-attribute defaults. Full
SampleScraper-driven materialization tests live in tests/test_scraper_sample.py
(W3).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from models import ApplicationBoard, JobSource
from scraper.base import ScraperBase
from scraper.types import RawJob, ScrapeQuery

pytestmark = pytest.mark.uses_sample_data_shims


def test_scraperbase_cannot_instantiate_directly():
    """ABC enforcement — abstract `scrape()` blocks direct construction."""
    with pytest.raises(TypeError, match="abstract"):
        ScraperBase()  # type: ignore[abstract]


def test_scraperbase_subclass_missing_scrape_cannot_instantiate():
    """Subclass that omits `scrape()` is still abstract."""

    class IncompleteScraper(ScraperBase):
        source = JobSource.MANUAL
        board = ApplicationBoard.MANUAL

    with pytest.raises(TypeError, match="abstract"):
        IncompleteScraper()  # type: ignore[abstract]


def test_scraperbase_subclass_with_scrape_constructs_cleanly():
    """A concrete subclass with `scrape()` implemented instantiates."""

    class ConcreteScraper(ScraperBase):
        source = JobSource.MANUAL
        board = ApplicationBoard.MANUAL

        async def scrape(self, query: ScrapeQuery) -> AsyncIterator[RawJob]:
            return
            yield  # pragma: no cover — generator marker

    # Inject a dummy client to avoid triggering the lazy Crawl4AIClient import
    # path; in production the default constructor wires the real client.
    instance = ConcreteScraper(client=object())  # type: ignore[arg-type]
    assert instance.source is JobSource.MANUAL
    assert instance.board is ApplicationBoard.MANUAL
    assert instance.name == "ConcreteScraper"
    assert instance._errors == []


def test_scraperbase_default_rate_limit_attributes():
    """Class-level defaults: 30 req/min + 1-3s jitter (plan § D.6)."""
    assert ScraperBase.rate_limit_per_minute == 30
    assert ScraperBase.random_delay_seconds == (1.0, 3.0)


def test_scraperbase_subclass_can_override_rate_limit():
    """Aggressive subclass override stays on the class, not propagated."""

    class FastScraper(ScraperBase):
        source = JobSource.MANUAL
        board = ApplicationBoard.MANUAL
        rate_limit_per_minute = 120
        random_delay_seconds = (0.1, 0.5)

        async def scrape(self, query: ScrapeQuery) -> AsyncIterator[RawJob]:
            return
            yield  # pragma: no cover

    assert FastScraper.rate_limit_per_minute == 120
    # Sibling default unaffected.
    assert ScraperBase.rate_limit_per_minute == 30


def test_scraperbase_name_property_returns_class_name():
    """`name` is the subclass name — used in JobScrapeRun.raw_meta diagnostics."""

    class MyExoticScraper(ScraperBase):
        source = JobSource.MANUAL
        board = ApplicationBoard.MANUAL

        async def scrape(self, query: ScrapeQuery) -> AsyncIterator[RawJob]:
            return
            yield  # pragma: no cover

    instance = MyExoticScraper(client=object())  # type: ignore[arg-type]
    assert instance.name == "MyExoticScraper"
