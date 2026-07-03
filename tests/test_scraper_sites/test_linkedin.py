"""LinkedIn scraper tests — plan 33 § D.8 (~7 tests)."""

from __future__ import annotations

import pytest

from models import ApplicationBoard, JobSource
from scraper import url_guard
from scraper.sites.linkedin import LinkedInScraper
from scraper.types import ScrapeQuery

from ._helpers import FakeClient, load_fixture

LIST_URL = (
    "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    "?keywords=python+engineer&location=San+Francisco&start=0&f_TPR=r604800"
)


@pytest.fixture(autouse=True)
def _stub_dns(monkeypatch):
    monkeypatch.setattr(url_guard, "_resolve_host", lambda host: ("93.184.216.34",) if host else ())


def _make_client(responses=None, raise_for_url=None) -> FakeClient:
    return FakeClient(responses=responses or {}, raise_for_url=raise_for_url or {})


@pytest.mark.asyncio
async def test_linkedin_listing_url_composition():
    """Composes the guest-API URL with URL-encoded keywords + last-7d filter."""
    scraper = LinkedInScraper(client=_make_client())  # type: ignore[arg-type]
    url = scraper._compose_listing_url(
        ScrapeQuery(keywords=["python", "engineer"], location="San Francisco")
    )
    assert url == LIST_URL
    safe, _ = url_guard.is_safe_destination(url)
    assert safe is True


@pytest.mark.asyncio
async def test_linkedin_hostile_query_url_rejected(monkeypatch):
    """A `company_filter` carrying userinfo flows through — guard blocks composed URL."""
    # We don't have a company_filter on LinkedIn, but the guard fires at
    # detail-URL composition; force the detail URL to fail by patching the host.
    scraper = LinkedInScraper(client=_make_client())  # type: ignore[arg-type]
    # Inject hostile resolver: linkedin.com resolves to 169.254.169.254 (IMDS).
    monkeypatch.setattr(url_guard, "_resolve_host", lambda host: ("169.254.169.254",))
    rawjobs = [j async for j in scraper.scrape(ScrapeQuery(keywords=["x"], location="y"))]
    assert rawjobs == []
    assert any("kind=url_guard_blocked" in e for e in scraper._errors)


@pytest.mark.asyncio
async def test_linkedin_listing_parse_extracts_external_id_from_urn():
    """`urn:li:jobPosting:<id>` regex pulls the numeric id."""
    client = _make_client(
        responses={
            LIST_URL: load_fixture("linkedin_listing.html"),
            "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/": load_fixture(
                "linkedin_detail.html"
            ),
        }
    )
    scraper = LinkedInScraper(client=client)  # type: ignore[arg-type]
    rawjobs = [
        j
        async for j in scraper.scrape(
            ScrapeQuery(keywords=["python", "engineer"], location="San Francisco")
        )
    ]
    assert len(rawjobs) == 3
    assert rawjobs[0].external_id == "3729012345"
    # Third card has no `data-entity-urn`; falls back to /jobs/view/<id>.
    assert rawjobs[2].external_id == "3729012347"
    assert all(j.source is JobSource.LINKEDIN for j in rawjobs)
    assert all(j.board is ApplicationBoard.LINKEDIN for j in rawjobs)


@pytest.mark.asyncio
async def test_linkedin_detail_parse_fills_description():
    """`<section class="description">` populates description_text."""
    client = _make_client(
        responses={
            LIST_URL: load_fixture("linkedin_listing.html"),
            "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/": load_fixture(
                "linkedin_detail.html"
            ),
        }
    )
    scraper = LinkedInScraper(client=client)  # type: ignore[arg-type]
    rawjobs = [
        j
        async for j in scraper.scrape(
            ScrapeQuery(keywords=["python", "engineer"], location="San Francisco")
        )
    ]
    assert rawjobs[0].description_text is not None
    assert "distributed systems" in rawjobs[0].description_text
    assert rawjobs[0].company_name == "Helios Labs" or rawjobs[0].company_name == "Acme Fake"


@pytest.mark.asyncio
async def test_linkedin_per_listing_error_continues_scraping():
    """Detail-fetch raise on one card skips it; others yield."""
    client = _make_client(
        responses={
            LIST_URL: load_fixture("linkedin_listing.html"),
            "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/3729012345": load_fixture(
                "linkedin_detail.html"
            ),
            "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/3729012347": load_fixture(
                "linkedin_detail.html"
            ),
        },
        raise_for_url={
            "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/3729012346": (
                RuntimeError("503")
            )
        },
    )
    scraper = LinkedInScraper(client=client)  # type: ignore[arg-type]
    rawjobs = [
        j
        async for j in scraper.scrape(
            ScrapeQuery(keywords=["python", "engineer"], location="San Francisco")
        )
    ]
    assert len(rawjobs) == 2
    assert any("kind=detail_fetch_failure" in e for e in scraper._errors)


@pytest.mark.asyncio
async def test_linkedin_provider_none_short_circuits_extraction():
    """Lazy import of services.job_extractor never fires when provider is None."""
    import sys

    sys.modules.pop("services.job_extractor", None)
    client = _make_client(
        responses={
            LIST_URL: load_fixture("linkedin_listing.html"),
            "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/": load_fixture(
                "linkedin_detail.html"
            ),
        }
    )
    scraper = LinkedInScraper(client=client)  # type: ignore[arg-type]
    [
        _
        async for _ in scraper.scrape(
            ScrapeQuery(keywords=["python", "engineer"], location="San Francisco")
        )
    ]
    assert "services.job_extractor" not in sys.modules


@pytest.mark.asyncio
async def test_linkedin_rsshub_fallback_when_primary_empty(monkeypatch):
    """When guest API returns no cards + `SCRAPER_RSSHUB_URL` set, fall back."""
    from config import settings

    monkeypatch.setattr(settings, "scraper_rsshub_url", "https://rsshub.example.net")
    rsshub_url = "https://rsshub.example.net/linkedin/jobs/python+engineer/San+Francisco"
    rss_xml = (
        "<rss><channel>"
        "<item>"
        "<title>Senior Engineer at Acme Fake</title>"
        "<link>https://www.linkedin.com/jobs/view/9999999999</link>"
        "<description>Build great things.</description>"
        "</item>"
        "</channel></rss>"
    )
    client = _make_client(
        responses={
            LIST_URL: "<html><body></body></html>",  # zero cards
            rsshub_url: rss_xml,
        }
    )
    scraper = LinkedInScraper(client=client)  # type: ignore[arg-type]
    rawjobs = [
        j
        async for j in scraper.scrape(
            ScrapeQuery(keywords=["python", "engineer"], location="San Francisco")
        )
    ]
    assert len(rawjobs) == 1
    assert rawjobs[0].external_id == "9999999999"
    assert rawjobs[0].raw_meta.get("via") == "rsshub"


# ── 2026-07 volume rework: pagination + known-ID skip ───────────────────

_PAGE2_URL = (
    "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    "?keywords=python+engineer&location=San+Francisco&start=25&f_TPR=r604800"
)

_PAGE2_HTML = """
<ul><li data-entity-urn="urn:li:jobPosting:9990000001">
  <div class="base-search-card__title">Staff Engineer</div>
  <div class="base-search-card__subtitle">Acme</div>
</li></ul>
"""


@pytest.mark.asyncio
async def test_linkedin_paginates_past_first_page():
    client = _make_client(
        responses={
            LIST_URL: load_fixture("linkedin_listing.html"),
            _PAGE2_URL: _PAGE2_HTML,
            "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/": load_fixture(
                "linkedin_detail.html"
            ),
        }
    )
    scraper = LinkedInScraper(client=client)  # type: ignore[arg-type]
    jobs = [
        j
        async for j in scraper.scrape(
            ScrapeQuery(keywords=["python", "engineer"], location="San Francisco")
        )
    ]
    ids = {j.external_id for j in jobs}
    assert "9990000001" in ids  # page-2 card reached
    assert any("start=25" in u for u in client.fetch_calls)


@pytest.mark.asyncio
async def test_linkedin_known_ids_skip_detail_fetch():
    client = _make_client(
        responses={
            LIST_URL: load_fixture("linkedin_listing.html"),
            "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/": load_fixture(
                "linkedin_detail.html"
            ),
        }
    )
    scraper = LinkedInScraper(client=client)  # type: ignore[arg-type]
    scraper.set_known_external_ids({"3729012345"})
    jobs = [
        j
        async for j in scraper.scrape(
            ScrapeQuery(keywords=["python", "engineer"], location="San Francisco")
        )
    ]
    assert all(j.external_id != "3729012345" for j in jobs)
    assert scraper._skipped_known == 1
    # The known job's detail endpoint was never fetched.
    assert not any(u.endswith("/jobPosting/3729012345") for u in client.fetch_calls)
