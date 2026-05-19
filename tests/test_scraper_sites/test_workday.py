"""Workday scraper tests — plan 33 § D.8 (~6 tests)."""

from __future__ import annotations

import pytest

from models import JobSource
from scraper import url_guard
from scraper.sites.workday import WorkdayScraper
from scraper.types import ScrapeQuery

from ._helpers import FakeClient, load_fixture

LIST_URL = "https://fakeco.wd1.myworkdayjobs.com/External"


@pytest.fixture(autouse=True)
def _stub_dns(monkeypatch):
    monkeypatch.setattr(url_guard, "_resolve_host", lambda host: ("93.184.216.34",) if host else ())


def _make_client(responses=None, raise_for_url=None) -> FakeClient:
    return FakeClient(responses=responses or {}, raise_for_url=raise_for_url or {})


@pytest.mark.asyncio
async def test_workday_tenant_spec_with_site():
    """`"fakeco/External"` → tenant=`fakeco` + site=`External`."""
    tenant, site = WorkdayScraper._parse_tenant_spec("fakeco/External")
    assert tenant == "fakeco"
    assert site == "External"


@pytest.mark.asyncio
async def test_workday_tenant_spec_without_site_defaults_external():
    tenant, site = WorkdayScraper._parse_tenant_spec("fakeco")
    assert tenant == "fakeco"
    assert site == "External"


@pytest.mark.asyncio
async def test_workday_listing_parse_extracts_requisition_id():
    """`/External/job/<loc>/<title>_R-<NNN>` → external_id=`R-NNN`."""
    client = _make_client(
        responses={
            LIST_URL: load_fixture("workday_listing.html"),
            "https://fakeco.wd1.myworkdayjobs.com/External/job/": load_fixture(
                "workday_detail.html"
            ),
        }
    )
    scraper = WorkdayScraper(client=client)  # type: ignore[arg-type]
    rawjobs = [j async for j in scraper.scrape(ScrapeQuery(company_filter=["fakeco/External"]))]
    assert len(rawjobs) == 3
    assert rawjobs[0].external_id == "R-123456"
    assert rawjobs[1].external_id == "R-234567"
    # Third uses JR<digits> shape — regex must match either.
    assert rawjobs[2].external_id == "JR98765"
    assert all(j.source is JobSource.WORKDAY for j in rawjobs)


@pytest.mark.asyncio
async def test_workday_detail_parse_fills_description():
    """`data-automation-id="jobPostingDescription"` populates description_text."""
    client = _make_client(
        responses={
            LIST_URL: load_fixture("workday_listing.html"),
            "https://fakeco.wd1.myworkdayjobs.com/External/job/": load_fixture(
                "workday_detail.html"
            ),
        }
    )
    scraper = WorkdayScraper(client=client)  # type: ignore[arg-type]
    rawjobs = [j async for j in scraper.scrape(ScrapeQuery(company_filter=["fakeco/External"]))]
    assert rawjobs[0].description_text is not None
    assert "distributed systems" in rawjobs[0].description_text
    assert rawjobs[0].location_raw == "Remote — USA"


@pytest.mark.asyncio
async def test_workday_no_tenants_yields_nothing(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "workday_companies", None)
    client = _make_client()
    scraper = WorkdayScraper(client=client)  # type: ignore[arg-type]
    rawjobs = [j async for j in scraper.scrape(ScrapeQuery())]
    assert rawjobs == []
    assert client.fetch_calls == []


@pytest.mark.asyncio
async def test_workday_provider_none_short_circuits_extraction():
    import sys

    sys.modules.pop("services.job_extractor", None)
    client = _make_client(
        responses={
            LIST_URL: load_fixture("workday_listing.html"),
            "https://fakeco.wd1.myworkdayjobs.com/External/job/": load_fixture(
                "workday_detail.html"
            ),
        }
    )
    scraper = WorkdayScraper(client=client)  # type: ignore[arg-type]
    [_ async for _ in scraper.scrape(ScrapeQuery(company_filter=["fakeco/External"]))]
    assert "services.job_extractor" not in sys.modules
