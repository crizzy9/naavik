"""Ashby job-board scraper.

Per docs/design/SCRAPER_SITES.md § Ashby (graduated from plan 33).

Per-company JSON-API endpoint:
- List: ``https://api.ashbyhq.com/posting-api/job-board/{company}?includeCompensation=true``
  Returns ``{"jobs": [...]}``. Each row carries ``id`` (UUID), ``title`` (str),
  ``jobUrl`` (str), ``location`` (str), ``employmentType`` (str),
  ``compensation`` (object), ``descriptionHtml`` (str), ``publishedAt`` (ISO).
- Detail: ``jobUrl`` already inlines the JD; we re-fetch HTML for AI extraction
  parity with Lever / Greenhouse.

External-ID rule: ``row["id"]`` (UUID).
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup

from config import settings
from models import ApplicationBoard, JobSource, RemotePolicy
from scraper.redaction import safe_exc, safe_url
from scraper.sites._base_site import _BaseSiteScraper
from scraper.types import RawJob, ScrapeQuery
from scraper.url_guard import is_safe_destination

log = logging.getLogger(__name__)


class AshbyScraper(_BaseSiteScraper):
    """Ashby posting-API scraper."""

    source = JobSource.ASHBY
    board = ApplicationBoard.ASHBY
    rate_limit_per_minute = 20
    random_delay_seconds = (1.5, 3.0)

    _LIST_TEMPLATE = (
        "https://api.ashbyhq.com/posting-api/job-board/{company}?includeCompensation=true"
    )

    async def scrape(self, query: ScrapeQuery) -> AsyncIterator[RawJob]:
        companies = self._resolve_companies(query)
        if not companies:
            log.info("ashby: no companies configured; nothing to scrape")
            return

        yielded = 0
        for company in companies:
            list_url = self._compose_url(self._LIST_TEMPLATE, stage="list", company=company)
            if list_url is None:
                continue
            safe, reason = is_safe_destination(list_url)
            if not safe:
                self._errors.append(
                    f"stage=list url={safe_url(list_url)} kind=url_guard_blocked msg={reason}"
                )
                continue

            try:
                payload = await self._fetch_listing_payload(list_url)
            except Exception as exc:  # noqa: BLE001 — tier-1
                self._errors.append(
                    f"stage=list url={safe_url(list_url)} "
                    f"kind=list_fetch_failure msg={safe_exc(exc)}"
                )
                continue

            for row in (payload or {}).get("jobs", []):
                if yielded >= query.max_listings:
                    return
                try:
                    raw_job = await self._build_raw_job(company=company, row=row)
                except Exception as exc:  # noqa: BLE001 — per-listing tolerance
                    detail_url = row.get("jobUrl") if isinstance(row, dict) else None
                    self._errors.append(
                        f"stage=detail url={safe_url(detail_url)} "
                        f"kind=parse_failure msg={safe_exc(exc)}"
                    )
                    continue
                if raw_job is None:
                    continue
                enriched = await self._maybe_enrich(raw_job)
                yielded += 1
                yield enriched

    def _resolve_companies(self, query: ScrapeQuery) -> list[str]:
        if query.company_filter:
            return [c for c in query.company_filter if c]
        return list(settings.ashby_companies or [])

    async def _fetch_listing_payload(self, list_url: str) -> dict[str, Any] | None:
        html = await self._client.fetch_html(list_url)
        if html is None:
            return None
        text = html.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            soup = BeautifulSoup(html, "html.parser")
            return json.loads(soup.get_text("\n").strip())

    async def _build_raw_job(
        self,
        *,
        company: str,
        row: dict[str, Any],
    ) -> RawJob | None:
        if not isinstance(row, dict):
            return None
        posting_id = row.get("id")
        title = row.get("title")
        job_url = row.get("jobUrl")
        if not posting_id or not title or not job_url:
            return None

        safe, reason = is_safe_destination(str(job_url))
        if not safe:
            self._errors.append(
                f"stage=detail url={safe_url(str(job_url))} kind=url_guard_blocked msg={reason}"
            )
            return None

        description_html = row.get("descriptionHtml")
        description_text = None
        if isinstance(description_html, str):
            description_text = BeautifulSoup(description_html, "html.parser").get_text("\n").strip()
        elif isinstance(row.get("descriptionPlain"), str):
            description_text = row["descriptionPlain"]

        location_raw = row.get("location") or row.get("locationName")
        if isinstance(location_raw, dict):
            location_raw = location_raw.get("name")

        remote_hint = None
        if row.get("isRemote") is True:
            remote_hint = RemotePolicy.REMOTE

        posted_at = self._parse_iso(row.get("publishedAt"))

        return RawJob(
            source=JobSource.ASHBY,
            external_id=str(posting_id),
            source_url=str(job_url),
            board=ApplicationBoard.ASHBY,
            url_type="external",
            company_name=company,
            position_title=str(title),
            location_raw=str(location_raw) if location_raw else None,
            description_html=description_html if isinstance(description_html, str) else None,
            description_text=description_text if isinstance(description_text, str) else None,
            posted_at=posted_at,
            remote_policy_hint=remote_hint,
            raw_meta={
                "company_slug": company,
                "employment_type": row.get("employmentType"),
            },
        )

    @staticmethod
    def _parse_iso(value: object) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
