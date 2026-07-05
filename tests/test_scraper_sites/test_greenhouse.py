"""Greenhouse scraper tests — plan 33 § D.8 (~6 tests)."""

from __future__ import annotations

import pytest

from models import JobSource
from scraper import url_guard
from scraper.sites.greenhouse import GreenhouseScraper
from scraper.types import ScrapeQuery

from ._helpers import FakeClient, load_fixture


@pytest.fixture(autouse=True)
def _stub_dns(monkeypatch):
    """Treat all hosts as public so the guard returns (True, None)."""
    monkeypatch.setattr(url_guard, "_resolve_host", lambda host: ("93.184.216.34",) if host else ())


def _make_client(responses=None, raise_for_url=None) -> FakeClient:
    return FakeClient(responses=responses or {}, raise_for_url=raise_for_url or {})


@pytest.mark.asyncio
async def test_greenhouse_listing_url_composition():
    """Composes the documented embed JSON URL + URL guard accepts it."""
    client = _make_client()
    scraper = GreenhouseScraper(client=client)  # type: ignore[arg-type]
    expected = "https://boards.greenhouse.io/embed/job_board?for=acmefake&format=json"
    safe, reason = url_guard.is_safe_destination(expected)
    assert safe is True
    assert reason is None
    assert GreenhouseScraper._LIST_TEMPLATE.format(company="acmefake") == expected
    # Smoke — no listings exist for an empty response, but URL composition runs.
    client.responses[expected] = "{}"
    rawjobs = [j async for j in scraper.scrape(ScrapeQuery(company_filter=["acmefake"]))]
    assert rawjobs == []


@pytest.mark.asyncio
async def test_greenhouse_listing_parse_extracts_external_id():
    """Feed the JSON fixture; first yielded RawJob carries the row's `id` as str."""
    list_url = "https://boards.greenhouse.io/embed/job_board?for=acmefake&format=json"
    detail_url_prefix = "https://boards.greenhouse.io/acmefake/jobs/"
    client = _make_client(
        responses={
            list_url: load_fixture("greenhouse_listing.json"),
            detail_url_prefix: load_fixture("greenhouse_detail.html"),
        }
    )
    scraper = GreenhouseScraper(client=client)  # type: ignore[arg-type]
    rawjobs = [j async for j in scraper.scrape(ScrapeQuery(company_filter=["acmefake"]))]
    assert len(rawjobs) == 3
    assert rawjobs[0].external_id == "5827341"
    assert rawjobs[0].source is JobSource.GREENHOUSE
    assert rawjobs[0].company_name == "acmefake"
    assert rawjobs[0].position_title == "Senior Backend Engineer"


@pytest.mark.asyncio
async def test_greenhouse_detail_parse_fills_required_fields():
    """`#content` div in the detail page populates description_text."""
    list_url = "https://boards.greenhouse.io/embed/job_board?for=acmefake&format=json"
    client = _make_client(
        responses={
            list_url: load_fixture("greenhouse_listing.json"),
            "https://boards.greenhouse.io/acmefake/jobs/": load_fixture("greenhouse_detail.html"),
        }
    )
    scraper = GreenhouseScraper(client=client)  # type: ignore[arg-type]
    rawjobs = [j async for j in scraper.scrape(ScrapeQuery(company_filter=["acmefake"]))]
    assert rawjobs[0].description_text is not None
    assert "Senior Backend Engineer" in rawjobs[0].description_text
    assert rawjobs[0].location_raw == "Remote — US"
    assert rawjobs[0].source_url.startswith("https://boards.greenhouse.io/acmefake/jobs/")


@pytest.mark.asyncio
async def test_greenhouse_no_companies_yields_nothing(monkeypatch):
    """No `company_filter` + no `Settings.greenhouse_companies` → empty iterator."""
    from config import settings

    monkeypatch.setattr(settings, "greenhouse_companies", None)
    client = _make_client()
    scraper = GreenhouseScraper(client=client)  # type: ignore[arg-type]
    rawjobs = [j async for j in scraper.scrape(ScrapeQuery())]
    assert rawjobs == []
    assert client.fetch_calls == []


@pytest.mark.asyncio
async def test_greenhouse_per_listing_error_continues_scraping():
    """Detail-fetch failure on one row appends a tier-1 error but skips the row."""
    list_url = "https://boards.greenhouse.io/embed/job_board?for=acmefake&format=json"
    raise_url = "https://boards.greenhouse.io/acmefake/jobs/5827342"
    client = _make_client(
        responses={
            list_url: load_fixture("greenhouse_listing.json"),
            "https://boards.greenhouse.io/acmefake/jobs/5827341": load_fixture(
                "greenhouse_detail.html"
            ),
            "https://boards.greenhouse.io/acmefake/jobs/5827343": load_fixture(
                "greenhouse_detail.html"
            ),
        },
        raise_for_url={raise_url: RuntimeError("503 from upstream")},
    )
    scraper = GreenhouseScraper(client=client)  # type: ignore[arg-type]
    rawjobs = [j async for j in scraper.scrape(ScrapeQuery(company_filter=["acmefake"]))]
    # The fixture has 3 rows; the middle one raised, so 2 yielded.
    assert len(rawjobs) == 2
    assert any("kind=parse_failure" in e for e in scraper._errors)


@pytest.mark.asyncio
async def test_greenhouse_provider_none_short_circuits_extraction(monkeypatch):
    """`provider=None` → `_maybe_enrich` returns RawJob unmodified, no service import."""
    import sys

    sys.modules.pop("services.job_extractor", None)
    list_url = "https://boards.greenhouse.io/embed/job_board?for=acmefake&format=json"
    client = _make_client(
        responses={
            list_url: load_fixture("greenhouse_listing.json"),
            "https://boards.greenhouse.io/acmefake/jobs/": load_fixture("greenhouse_detail.html"),
        }
    )
    scraper = GreenhouseScraper(client=client)  # type: ignore[arg-type]
    rawjobs = [j async for j in scraper.scrape(ScrapeQuery(company_filter=["acmefake"]))]
    assert len(rawjobs) == 3
    # Lazy import never fired because provider is None.
    assert "services.job_extractor" not in sys.modules


# ── Plan 43 § D.5.5 — hostile company slug → no fetch ─────────────────────


@pytest.mark.asyncio
async def test_greenhouse_hostile_company_skipped_with_invalid_slug_error():
    """Hostile `company` slug rejected BEFORE URL composition."""
    client = _make_client()
    scraper = GreenhouseScraper(client=client)  # type: ignore[arg-type]
    rawjobs = [j async for j in scraper.scrape(ScrapeQuery(company_filter=["acme&for=victim"]))]

    assert rawjobs == []
    assert client.fetch_calls == []
    assert any("kind=invalid_slug" in e for e in scraper._errors)
    assert any("msg=company=" in e for e in scraper._errors)


@pytest.mark.asyncio
async def test_greenhouse_skips_known_ids_before_detail_fetch():
    """Plan 91 5.2 — listings already in the library never hit the detail
    page. Indeed/LinkedIn had this guard; greenhouse re-fetched every
    detail page on every cron run."""
    list_url = "https://boards.greenhouse.io/embed/job_board?for=acmefake&format=json"
    detail_url_prefix = "https://boards.greenhouse.io/acmefake/jobs/"
    client = _make_client(
        responses={
            list_url: load_fixture("greenhouse_listing.json"),
            detail_url_prefix: load_fixture("greenhouse_detail.html"),
        }
    )
    scraper = GreenhouseScraper(client=client)  # type: ignore[arg-type]
    scraper.set_known_external_ids({"5827341"})  # first fixture row

    rawjobs = [j async for j in scraper.scrape(ScrapeQuery(company_filter=["acmefake"]))]

    assert {j.external_id for j in rawjobs} == {
        j.external_id for j in rawjobs if j.external_id != "5827341"
    }
    assert len(rawjobs) == 2  # fixture carries 3 rows; the known one skipped
    assert scraper._skipped_known == 1
    # The known listing's detail page was never fetched: one list fetch +
    # one detail fetch per YIELDED job only.
    detail_fetches = [u for u in client.fetch_calls if u.startswith(detail_url_prefix)]
    assert len(detail_fetches) == 2
