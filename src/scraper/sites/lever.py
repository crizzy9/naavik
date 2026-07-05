"""Lever job-board scraper.

Per docs/design/SCRAPER_SITES.md § Lever (graduated from plan 33).

Per-company JSON-API endpoint:
- List: ``https://api.lever.co/v0/postings/{company}?mode=json``
  Returns a flat JSON array. Each row carries ``id`` (UUID-shaped str),
  ``text`` (str, the title), ``categories.team`` (str), ``categories.location``
  (str), ``categories.commitment`` (str), ``description`` (str), ``hostedUrl``
  (str), ``createdAt`` (ms epoch).
- Detail: each row carries ``hostedUrl`` directly; description body is also
  inlined as ``descriptionPlain`` / ``description`` — no second fetch needed
  for the JD body, but we re-fetch the HTML for rich formatting + future AI
  extraction.

External-ID rule: ``row["id"]`` from the JSON-API row (UUID string).
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from bs4 import BeautifulSoup

from config import settings
from models import ApplicationBoard, JobSource
from scraper.redaction import safe_exc, safe_url
from scraper.sites._base_site import _BaseSiteScraper
from scraper.types import RawJob, ScrapeQuery
from scraper.url_guard import is_safe_destination
from services.utils.html_text import fragment_text

log = logging.getLogger(__name__)


class LeverScraper(_BaseSiteScraper):
    """Lever postings-API scraper."""

    source = JobSource.LEVER
    board = ApplicationBoard.LEVER
    rate_limit_per_minute = 20
    random_delay_seconds = (1.5, 3.0)

    _LIST_TEMPLATE = "https://api.lever.co/v0/postings/{company}?mode=json"

    async def scrape(self, query: ScrapeQuery) -> AsyncIterator[RawJob]:
        companies = self._resolve_companies(query)
        if not companies:
            log.info("lever: no companies configured; nothing to scrape")
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
                rows = await self._fetch_listing_array(list_url)
            except Exception as exc:  # noqa: BLE001 — tier-1
                self._errors.append(
                    f"stage=list url={safe_url(list_url)} "
                    f"kind=list_fetch_failure msg={safe_exc(exc)}"
                )
                continue

            for row in rows or []:
                if yielded >= query.max_listings:
                    return
                try:
                    raw_job = await self._build_raw_job(company=company, row=row)
                except Exception as exc:  # noqa: BLE001 — per-listing tolerance
                    detail_url = row.get("hostedUrl") if isinstance(row, dict) else None
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
        return list(settings.lever_companies or [])

    async def _fetch_listing_array(self, list_url: str) -> list[dict[str, Any]] | None:
        html = await self._client.fetch_html(list_url)
        if html is None:
            return None
        text = html.strip()
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            soup = BeautifulSoup(html, "html.parser")
            payload = json.loads(soup.get_text("\n").strip())
        if not isinstance(payload, list):
            return None
        return payload

    async def _build_raw_job(
        self,
        *,
        company: str,
        row: dict[str, Any],
    ) -> RawJob | None:
        if not isinstance(row, dict):
            return None
        posting_id = row.get("id")
        title = row.get("text")
        hosted_url = row.get("hostedUrl")
        if not posting_id or not title or not hosted_url:
            return None

        safe, reason = is_safe_destination(str(hosted_url))
        if not safe:
            self._errors.append(
                f"stage=detail url={safe_url(str(hosted_url))} kind=url_guard_blocked msg={reason}"
            )
            return None

        # JSON payload usually carries description; HTML detail is optional.
        description_html = row.get("description")
        description_text = row.get("descriptionPlain")
        if not description_text and isinstance(description_html, str):
            description_text = fragment_text(description_html) or ""

        categories = row.get("categories") or {}
        location_raw = None
        if isinstance(categories, dict):
            location_raw = categories.get("location") or categories.get("allLocations")
            if isinstance(location_raw, list):
                location_raw = ", ".join(str(x) for x in location_raw if x)

        posted_at = self._parse_epoch_ms(row.get("createdAt"))

        return RawJob(
            source=JobSource.LEVER,
            external_id=str(posting_id),
            source_url=str(hosted_url),
            board=ApplicationBoard.LEVER,
            url_type="external",
            company_name=company,
            position_title=str(title),
            location_raw=str(location_raw) if location_raw else None,
            description_html=str(description_html) if isinstance(description_html, str) else None,
            description_text=description_text if isinstance(description_text, str) else None,
            posted_at=posted_at,
            raw_meta={
                "company_slug": company,
                "team": categories.get("team") if isinstance(categories, dict) else None,
                "commitment": categories.get("commitment")
                if isinstance(categories, dict)
                else None,
            },
        )

    @staticmethod
    def _parse_epoch_ms(value: object) -> datetime | None:
        if not isinstance(value, int | float):
            return None
        try:
            return datetime.fromtimestamp(float(value) / 1000.0, tz=UTC)
        except (OverflowError, ValueError):
            return None
