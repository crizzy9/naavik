"""Greenhouse job-board scraper.

Per docs/design/SCRAPER_SITES.md § Greenhouse (graduated from plan 33).

Per-company JSON-API endpoint:
- List: ``https://boards.greenhouse.io/embed/job_board?for={company}&format=json``
  Returns a flat JSON object with a ``jobs`` array. Each row carries
  ``id`` (int) + ``title`` (str) + ``absolute_url`` (str) + ``location.name``
  (str) + ``updated_at`` (ISO datetime).
- Detail: ``https://boards.greenhouse.io/{company}/jobs/{id}`` (HTML page;
  ``#content`` body is the JD).

External-ID rule: ``str(row["id"])`` from the JSON-API row. Stable +
unique within `(company, greenhouse)`.

`ScrapeQuery.company_filter` is the canonical input; if it's None / empty,
fall back to `Settings.greenhouse_companies` from env. If both are unset,
yield nothing — cron skips silently.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup

from config import settings
from models import ApplicationBoard, JobSource
from scraper.redaction import safe_exc, safe_url
from scraper.sites._base_site import _BaseSiteScraper
from scraper.types import RawJob, ScrapeQuery
from scraper.url_guard import is_safe_destination

log = logging.getLogger(__name__)


class GreenhouseScraper(_BaseSiteScraper):
    """Greenhouse embed-API scraper.

    Class-level rate limit (20/min) tuned for the JSON-API endpoint;
    `0.2.0.13` lifts per-source tuning into operator-controlled Settings.
    """

    source = JobSource.GREENHOUSE
    board = ApplicationBoard.GREENHOUSE
    rate_limit_per_minute = 20
    random_delay_seconds = (1.5, 3.0)

    _LIST_TEMPLATE = "https://boards.greenhouse.io/embed/job_board?for={company}&format=json"
    _DETAIL_TEMPLATE = "https://boards.greenhouse.io/{company}/jobs/{job_id}"

    async def scrape(self, query: ScrapeQuery) -> AsyncIterator[RawJob]:
        companies = self._resolve_companies(query)
        if not companies:
            log.info("greenhouse: no companies configured; nothing to scrape")
            return

        yielded = 0
        for company in companies:
            list_url = self._LIST_TEMPLATE.format(company=company)
            safe, reason = is_safe_destination(list_url)
            if not safe:
                self._errors.append(
                    f"stage=list url={safe_url(list_url)} kind=url_guard_blocked msg={reason}"
                )
                continue

            try:
                payload = await self._fetch_listing_payload(list_url)
            except Exception as exc:  # noqa: BLE001 — tier-1 per SCRAPER_BASE.md § H.1
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
                    self._errors.append(
                        f"stage=detail url={safe_url(self._row_detail_url(company, row))} "
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
        return list(settings.greenhouse_companies or [])

    @staticmethod
    def _row_detail_url(company: str, row: dict[str, Any]) -> str:
        if isinstance(row.get("absolute_url"), str) and row["absolute_url"]:
            return str(row["absolute_url"])
        return GreenhouseScraper._DETAIL_TEMPLATE.format(
            company=company, job_id=row.get("id", "unknown")
        )

    async def _fetch_listing_payload(self, list_url: str) -> dict[str, Any] | None:
        html = await self._client.fetch_html(list_url)
        if html is None:
            return None
        # Crawl4AI returns the rendered HTML page; the JSON endpoint either
        # comes back as a bare JSON document or wrapped in a `<pre>` block by
        # the headless browser. Try both shapes.
        text = html.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            soup = BeautifulSoup(html, "html.parser")
            body = soup.get_text("\n").strip()
            return json.loads(body)

    async def _build_raw_job(
        self,
        *,
        company: str,
        row: dict[str, Any],
    ) -> RawJob | None:
        job_id = row.get("id")
        title = row.get("title")
        if job_id in (None, "") or not title:
            return None
        detail_url = self._row_detail_url(company, row)
        safe, reason = is_safe_destination(detail_url)
        if not safe:
            self._errors.append(
                f"stage=detail url={safe_url(detail_url)} kind=url_guard_blocked msg={reason}"
            )
            return None

        detail_html = await self._client.fetch_html(detail_url)
        description_text, description_html = self._extract_description(detail_html)

        location_raw = None
        location_obj = row.get("location")
        if isinstance(location_obj, dict):
            location_raw = location_obj.get("name")
        elif isinstance(location_obj, str):
            location_raw = location_obj

        posted_at = self._parse_iso(row.get("updated_at"))

        return RawJob(
            source=JobSource.GREENHOUSE,
            external_id=str(job_id),
            source_url=detail_url,
            board=ApplicationBoard.GREENHOUSE,
            url_type="external",
            company_name=company,
            position_title=str(title),
            location_raw=location_raw,
            description_html=description_html,
            description_text=description_text,
            posted_at=posted_at,
            posted_at_text=row.get("updated_at")
            if isinstance(row.get("updated_at"), str)
            else None,
            raw_meta={"company_slug": company},
        )

    @staticmethod
    def _extract_description(html: str | None) -> tuple[str | None, str | None]:
        if not html:
            return None, None
        soup = BeautifulSoup(html, "html.parser")
        content = soup.select_one("#content") or soup.select_one("div.app-body") or soup.body
        if content is None:
            return None, html
        return content.get_text("\n").strip() or None, str(content)

    @staticmethod
    def _parse_iso(value: object) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
