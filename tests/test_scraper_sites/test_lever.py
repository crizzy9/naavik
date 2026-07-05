"""Lever scraper tests — plan 33 § D.8 (~5 tests)."""

from __future__ import annotations

import pytest

from models import JobSource
from scraper import url_guard
from scraper.sites.lever import LeverScraper
from scraper.types import ScrapeQuery

from ._helpers import FakeClient, load_fixture


@pytest.fixture(autouse=True)
def _stub_dns(monkeypatch):
    monkeypatch.setattr(url_guard, "_resolve_host", lambda host: ("93.184.216.34",) if host else ())


def _make_client(responses=None, raise_for_url=None) -> FakeClient:
    return FakeClient(responses=responses or {}, raise_for_url=raise_for_url or {})


@pytest.mark.asyncio
async def test_lever_listing_url_composition():
    expected = "https://api.lever.co/v0/postings/fakecorp?mode=json"
    safe, _ = url_guard.is_safe_destination(expected)
    assert safe is True
    assert LeverScraper._LIST_TEMPLATE.format(company="fakecorp") == expected


@pytest.mark.asyncio
async def test_lever_listing_parse_extracts_external_id():
    list_url = "https://api.lever.co/v0/postings/fakecorp?mode=json"
    client = _make_client(
        responses={
            list_url: load_fixture("lever_listing.json"),
            "https://jobs.lever.co/fakecorp/": load_fixture("lever_detail.html"),
        }
    )
    scraper = LeverScraper(client=client)  # type: ignore[arg-type]
    rawjobs = [j async for j in scraper.scrape(ScrapeQuery(company_filter=["fakecorp"]))]
    assert len(rawjobs) == 2
    assert rawjobs[0].external_id == "abc12345-6789-4def-9012-3456789abcde"
    assert rawjobs[0].source is JobSource.LEVER
    assert rawjobs[0].company_name == "fakecorp"
    assert rawjobs[0].position_title == "Software Engineer, Platform"


@pytest.mark.asyncio
async def test_lever_inlined_description_populates_text():
    """Lever inlines description in the JSON payload — no second fetch needed."""
    list_url = "https://api.lever.co/v0/postings/fakecorp?mode=json"
    client = _make_client(responses={list_url: load_fixture("lever_listing.json")})
    scraper = LeverScraper(client=client)  # type: ignore[arg-type]
    rawjobs = [j async for j in scraper.scrape(ScrapeQuery(company_filter=["fakecorp"]))]
    assert rawjobs[0].description_text is not None
    assert "core platform" in rawjobs[0].description_text
    assert rawjobs[0].location_raw == "Remote — Americas"


@pytest.mark.asyncio
async def test_lever_no_companies_yields_nothing(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "lever_companies", None)
    client = _make_client()
    scraper = LeverScraper(client=client)  # type: ignore[arg-type]
    rawjobs = [j async for j in scraper.scrape(ScrapeQuery())]
    assert rawjobs == []


@pytest.mark.asyncio
async def test_lever_listing_fetch_failure_records_tier1_error():
    list_url = "https://api.lever.co/v0/postings/fakecorp?mode=json"
    client = _make_client(raise_for_url={list_url: RuntimeError("503")})
    scraper = LeverScraper(client=client)  # type: ignore[arg-type]
    rawjobs = [j async for j in scraper.scrape(ScrapeQuery(company_filter=["fakecorp"]))]
    assert rawjobs == []
    assert any("kind=list_fetch_failure" in e for e in scraper._errors)


@pytest.mark.asyncio
async def test_lever_provider_none_short_circuits_extraction():
    import sys

    sys.modules.pop("services.jobs.extractor", None)
    list_url = "https://api.lever.co/v0/postings/fakecorp?mode=json"
    client = _make_client(responses={list_url: load_fixture("lever_listing.json")})
    scraper = LeverScraper(client=client)  # type: ignore[arg-type]
    [_ async for _ in scraper.scrape(ScrapeQuery(company_filter=["fakecorp"]))]
    assert "services.jobs.extractor" not in sys.modules


# ── Plan 43 § D.5.4 — PR #102 path-traversal attack ───────────────────────


@pytest.mark.asyncio
async def test_lever_hostile_company_slash_injection_skipped():
    """PR #102 Finding #2 — `company="acme/../v0/users/{id}"` MUST NOT compose.

    Lever inlines `{company}` at the URL PATH position
    (`https://api.lever.co/v0/postings/{company}?mode=json`); a slash
    injection smuggles a path traversal. Slug regex rejects `/`, `.`, and
    `{}` — URL never composed, no fetch.
    """
    client = _make_client()
    scraper = LeverScraper(client=client)  # type: ignore[arg-type]
    rawjobs = [
        j async for j in scraper.scrape(ScrapeQuery(company_filter=["acme/../v0/users/{id}"]))
    ]

    assert rawjobs == []
    assert client.fetch_calls == []
    assert any("kind=invalid_slug" in e for e in scraper._errors)
    assert any("msg=company=" in e for e in scraper._errors)
