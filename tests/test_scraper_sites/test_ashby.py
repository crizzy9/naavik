"""Ashby scraper tests — plan 33 § D.8 (~5 tests)."""

from __future__ import annotations

import pytest

from models import JobSource, RemotePolicy
from scraper import url_guard
from scraper.sites.ashby import AshbyScraper
from scraper.types import ScrapeQuery

from ._helpers import FakeClient, load_fixture


@pytest.fixture(autouse=True)
def _stub_dns(monkeypatch):
    monkeypatch.setattr(url_guard, "_resolve_host", lambda host: ("93.184.216.34",) if host else ())


def _make_client(responses=None) -> FakeClient:
    return FakeClient(responses=responses or {})


@pytest.mark.asyncio
async def test_ashby_listing_url_composition():
    expected = "https://api.ashbyhq.com/posting-api/job-board/fakelabs?includeCompensation=true"
    safe, _ = url_guard.is_safe_destination(expected)
    assert safe is True
    assert AshbyScraper._LIST_TEMPLATE.format(company="fakelabs") == expected


@pytest.mark.asyncio
async def test_ashby_listing_parse_extracts_external_id():
    list_url = "https://api.ashbyhq.com/posting-api/job-board/fakelabs?includeCompensation=true"
    client = _make_client(
        responses={
            list_url: load_fixture("ashby_listing.json"),
            "https://jobs.ashbyhq.com/fakelabs/": load_fixture("ashby_detail.html"),
        }
    )
    scraper = AshbyScraper(client=client)  # type: ignore[arg-type]
    rawjobs = [j async for j in scraper.scrape(ScrapeQuery(company_filter=["fakelabs"]))]
    assert len(rawjobs) == 2
    assert rawjobs[0].external_id == "01234567-89ab-cdef-0123-456789abcdef"
    assert rawjobs[0].source is JobSource.ASHBY


@pytest.mark.asyncio
async def test_ashby_remote_hint_from_isremote_flag():
    """`isRemote: true` rows carry `remote_policy_hint=REMOTE`."""
    list_url = "https://api.ashbyhq.com/posting-api/job-board/fakelabs?includeCompensation=true"
    client = _make_client(responses={list_url: load_fixture("ashby_listing.json")})
    scraper = AshbyScraper(client=client)  # type: ignore[arg-type]
    rawjobs = [j async for j in scraper.scrape(ScrapeQuery(company_filter=["fakelabs"]))]
    # Row 0 isRemote=false → None; row 1 isRemote=true → REMOTE.
    assert rawjobs[0].remote_policy_hint is None
    assert rawjobs[1].remote_policy_hint is RemotePolicy.REMOTE


@pytest.mark.asyncio
async def test_ashby_no_companies_yields_nothing(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "ashby_companies", None)
    client = _make_client()
    scraper = AshbyScraper(client=client)  # type: ignore[arg-type]
    rawjobs = [j async for j in scraper.scrape(ScrapeQuery())]
    assert rawjobs == []


@pytest.mark.asyncio
async def test_ashby_description_html_populates_text():
    list_url = "https://api.ashbyhq.com/posting-api/job-board/fakelabs?includeCompensation=true"
    client = _make_client(responses={list_url: load_fixture("ashby_listing.json")})
    scraper = AshbyScraper(client=client)  # type: ignore[arg-type]
    rawjobs = [j async for j in scraper.scrape(ScrapeQuery(company_filter=["fakelabs"]))]
    assert rawjobs[0].description_text is not None
    assert "multi-region database" in rawjobs[0].description_text


@pytest.mark.asyncio
async def test_ashby_max_listings_cap_honored():
    list_url = "https://api.ashbyhq.com/posting-api/job-board/fakelabs?includeCompensation=true"
    client = _make_client(responses={list_url: load_fixture("ashby_listing.json")})
    scraper = AshbyScraper(client=client)  # type: ignore[arg-type]
    rawjobs = [
        j async for j in scraper.scrape(ScrapeQuery(company_filter=["fakelabs"], max_listings=1))
    ]
    assert len(rawjobs) == 1


# ── Plan 43 § D.5.5 — hostile company slug → no fetch ─────────────────────


@pytest.mark.asyncio
async def test_ashby_hostile_company_skipped_with_invalid_slug_error():
    """Hostile `company` slug rejected BEFORE URL composition."""
    client = _make_client()
    scraper = AshbyScraper(client=client)  # type: ignore[arg-type]
    rawjobs = [j async for j in scraper.scrape(ScrapeQuery(company_filter=["evil.com#"]))]

    assert rawjobs == []
    assert client.fetch_calls == []
    assert any("kind=invalid_slug" in e for e in scraper._errors)
    assert any("msg=company=" in e for e in scraper._errors)
