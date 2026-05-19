"""Indeed scraper tests — plan 33 § D.8 (~6 tests)."""

from __future__ import annotations

import pytest

from models import JobSource
from scraper import url_guard
from scraper.sites.indeed import IndeedScraper
from scraper.types import ScrapeQuery

from ._helpers import FakeClient, load_fixture

LIST_URL = "https://www.indeed.com/jobs?q=python+engineer&l=Remote"


@pytest.fixture(autouse=True)
def _stub_dns(monkeypatch):
    monkeypatch.setattr(url_guard, "_resolve_host", lambda host: ("93.184.216.34",) if host else ())


def _make_client(responses=None, raise_for_url=None) -> FakeClient:
    return FakeClient(responses=responses or {}, raise_for_url=raise_for_url or {})


@pytest.mark.asyncio
async def test_indeed_listing_url_composition():
    """`?q=<kw>&l=<loc>` with URL-encoded values."""
    scraper = IndeedScraper(client=_make_client())  # type: ignore[arg-type]
    url = scraper._compose_listing_url(
        ScrapeQuery(keywords=["python", "engineer"], location="Remote")
    )
    assert url == LIST_URL
    safe, _ = url_guard.is_safe_destination(url)
    assert safe is True


@pytest.mark.asyncio
async def test_indeed_listing_parse_extracts_jk():
    """`data-jk` attribute is the canonical external_id source."""
    client = _make_client(
        responses={
            LIST_URL: load_fixture("indeed_listing.html"),
            "https://www.indeed.com/viewjob": load_fixture("indeed_detail.html"),
        }
    )
    scraper = IndeedScraper(client=client)  # type: ignore[arg-type]
    rawjobs = [
        j
        async for j in scraper.scrape(
            ScrapeQuery(keywords=["python", "engineer"], location="Remote")
        )
    ]
    assert len(rawjobs) == 3
    assert rawjobs[0].external_id == "abc123def456"
    assert rawjobs[1].external_id == "789fedcba012"
    assert rawjobs[2].external_id == "345abc678def"
    assert all(j.source is JobSource.INDEED for j in rawjobs)


@pytest.mark.asyncio
async def test_indeed_detail_parse_fills_description():
    """`#jobDescriptionText` populates description_text."""
    client = _make_client(
        responses={
            LIST_URL: load_fixture("indeed_listing.html"),
            "https://www.indeed.com/viewjob": load_fixture("indeed_detail.html"),
        }
    )
    scraper = IndeedScraper(client=client)  # type: ignore[arg-type]
    rawjobs = [
        j
        async for j in scraper.scrape(
            ScrapeQuery(keywords=["python", "engineer"], location="Remote")
        )
    ]
    assert rawjobs[0].description_text is not None
    assert "Senior Software Engineer" in rawjobs[0].description_text
    assert rawjobs[0].company_name == "Acme Fake"


@pytest.mark.asyncio
async def test_indeed_per_listing_error_continues_scraping():
    """Detail-fetch raise skips that listing; others yield."""
    client = _make_client(
        responses={
            LIST_URL: load_fixture("indeed_listing.html"),
            "https://www.indeed.com/viewjob?jk=abc123def456": load_fixture("indeed_detail.html"),
            "https://www.indeed.com/viewjob?jk=345abc678def": load_fixture("indeed_detail.html"),
        },
        raise_for_url={"https://www.indeed.com/viewjob?jk=789fedcba012": RuntimeError("503")},
    )
    scraper = IndeedScraper(client=client)  # type: ignore[arg-type]
    rawjobs = [
        j
        async for j in scraper.scrape(
            ScrapeQuery(keywords=["python", "engineer"], location="Remote")
        )
    ]
    assert len(rawjobs) == 2
    assert any("kind=detail_fetch_failure" in e for e in scraper._errors)


@pytest.mark.asyncio
async def test_indeed_listing_fetch_failure_yields_nothing():
    client = _make_client(raise_for_url={LIST_URL: RuntimeError("403")})
    scraper = IndeedScraper(client=client)  # type: ignore[arg-type]
    rawjobs = [
        j
        async for j in scraper.scrape(
            ScrapeQuery(keywords=["python", "engineer"], location="Remote")
        )
    ]
    assert rawjobs == []
    assert any("kind=list_fetch_failure" in e for e in scraper._errors)


@pytest.mark.asyncio
async def test_indeed_provider_none_short_circuits_extraction():
    import sys

    sys.modules.pop("services.job_extractor", None)
    client = _make_client(
        responses={
            LIST_URL: load_fixture("indeed_listing.html"),
            "https://www.indeed.com/viewjob": load_fixture("indeed_detail.html"),
        }
    )
    scraper = IndeedScraper(client=client)  # type: ignore[arg-type]
    [
        _
        async for _ in scraper.scrape(
            ScrapeQuery(keywords=["python", "engineer"], location="Remote")
        )
    ]
    assert "services.job_extractor" not in sys.modules
