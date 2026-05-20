"""LinkedIn job-discovery scraper.

Per docs/design/research/LINKEDIN_SCRAPING.md § 5 + docs/design/SCRAPER_SITES.md
§ LinkedIn (graduated from plan 33 § D.6.2). Option B — direct guest API +
Crawl4AI stealth. RSShub fallback opt-in via `Settings.scraper_rsshub_url`.

URL patterns (unauthenticated guest API):
- Search: ``https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search``
  Query params: ``keywords``, ``location``, ``start`` (page offset),
  ``f_TPR`` (time filter — `r604800` = last 7 days).
- Detail: ``https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}``

Rate limit: 0.4 req/min (24/hour) per research § 5 trade-off accepted.
Conservative bound. Random delay 3-7s.

External-ID derivation: ``data-entity-urn="urn:li:jobPosting:<id>"`` on the
listing card, OR the path segment in ``href="/jobs/view/<id>/..."`` as
fallback when the urn attribute is missing.

RSShub fallback: when ``Settings.scraper_rsshub_url`` is set AND the guest
API returns nothing (HTTP failure or zero results), the scraper attempts
``{base}/linkedin/jobs/{keywords}/{location}`` as a secondary source. Off by
default.
"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from datetime import datetime
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from config import settings
from models import ApplicationBoard, JobSource
from scraper.redaction import safe_exc, safe_url
from scraper.sites._base_site import _BaseSiteScraper
from scraper.types import RawJob, ScrapeQuery
from scraper.url_guard import is_safe_destination

log = logging.getLogger(__name__)

_URN_RE = re.compile(r"urn:li:jobPosting:(\d+)")
_VIEW_HREF_RE = re.compile(r"/jobs/view/(\d+)")


class LinkedInScraper(_BaseSiteScraper):
    """LinkedIn guest-API scraper.

    Conservative: ~24 listings/hour ceiling (`rate_limit_per_minute = 0.4`
    -> 1 request per 150s in `Crawl4AIClient._enforce_min_interval`).
    RSShub fallback only when explicitly configured.
    """

    source = JobSource.LINKEDIN
    board = ApplicationBoard.LINKEDIN
    # 0.4 req/min = effective <=24/hr per research § 5. Plan 38 § D.8
    # promoted `rate_limit_per_minute` from `int` to `float`, so 0.4 no
    # longer floors to 1.
    rate_limit_per_minute = 0.4
    random_delay_seconds = (3.0, 7.0)

    _LIST_BASE = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    _DETAIL_BASE = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/"
    _FALLBACK_VIEW_BASE = "https://www.linkedin.com/jobs/view/"

    async def scrape(self, query: ScrapeQuery) -> AsyncIterator[RawJob]:
        list_url = self._compose_listing_url(query)
        safe, reason = is_safe_destination(list_url)
        if not safe:
            self._errors.append(
                f"stage=list url={safe_url(list_url)} kind=url_guard_blocked msg={reason}"
            )
            return

        listing_html: str | None = None
        try:
            listing_html = await self._client.fetch_html(list_url)
        except Exception as exc:  # noqa: BLE001 — tier-1
            self._errors.append(
                f"stage=list url={safe_url(list_url)} kind=list_fetch_failure msg={safe_exc(exc)}"
            )

        cards = self._parse_listing_cards(listing_html) if listing_html else []

        # RSShub fallback when nothing returned + operator configured a base URL.
        if not cards and settings.scraper_rsshub_url:
            async for raw in self._scrape_rsshub(query):
                yield raw
            return

        yielded = 0
        for card in cards:
            if yielded >= query.max_listings:
                return
            external_id = card.get("external_id")
            if not external_id:
                continue
            detail_url = f"{self._DETAIL_BASE}{external_id}"
            safe_d, reason_d = is_safe_destination(detail_url)
            if not safe_d:
                self._errors.append(
                    f"stage=detail url={safe_url(detail_url)} kind=url_guard_blocked msg={reason_d}"
                )
                continue
            try:
                detail_html = await self._client.fetch_html(detail_url)
            except Exception as exc:  # noqa: BLE001 — per-listing tolerance
                self._errors.append(
                    f"stage=detail url={safe_url(detail_url)} "
                    f"kind=detail_fetch_failure msg={safe_exc(exc)}"
                )
                continue
            raw_job = self._build_raw_job(
                external_id=external_id,
                detail_url=detail_url,
                card=card,
                detail_html=detail_html,
            )
            if raw_job is None:
                continue
            enriched = await self._maybe_enrich(raw_job)
            yielded += 1
            yield enriched

    def _compose_listing_url(self, query: ScrapeQuery) -> str:
        keywords = " ".join(query.keywords) if query.keywords else ""
        location = query.location or ""
        return (
            f"{self._LIST_BASE}?keywords={quote_plus(keywords)}"
            f"&location={quote_plus(location)}&start=0&f_TPR=r604800"
        )

    @staticmethod
    def _parse_listing_cards(html: str) -> list[dict[str, str | None]]:
        soup = BeautifulSoup(html, "html.parser")
        cards: list[dict[str, str | None]] = []
        for li in soup.select("li"):
            ext_id = LinkedInScraper._extract_external_id(li)
            if not ext_id:
                continue
            title_el = li.select_one(".base-search-card__title")
            company_el = li.select_one(".base-search-card__subtitle")
            location_el = li.select_one(".job-search-card__location")
            datetime_el = li.select_one("time")
            cards.append(
                {
                    "external_id": ext_id,
                    "title": title_el.get_text(strip=True) if title_el else None,
                    "company": company_el.get_text(strip=True) if company_el else None,
                    "location": location_el.get_text(strip=True) if location_el else None,
                    "posted_at_text": datetime_el.get("datetime") if datetime_el else None,
                }
            )
        return cards

    @staticmethod
    def _extract_external_id(li) -> str | None:  # type: ignore[no-untyped-def]
        urn = li.get("data-entity-urn") if hasattr(li, "get") else None
        if urn:
            m = _URN_RE.search(str(urn))
            if m:
                return m.group(1)
        # Fallback: any <a href="/jobs/view/<id>"> inside the card.
        for a in li.select("a[href]"):
            href = a.get("href", "")
            m = _VIEW_HREF_RE.search(str(href))
            if m:
                return m.group(1)
        return None

    @staticmethod
    def _build_raw_job(
        *,
        external_id: str,
        detail_url: str,
        card: dict[str, str | None],
        detail_html: str | None,
    ) -> RawJob | None:
        title = card.get("title") or "Unknown Title"
        company = card.get("company") or "Unknown Company"
        description_text = None
        description_html_clean = None
        if detail_html:
            soup = BeautifulSoup(detail_html, "html.parser")
            body = soup.select_one("section.description") or soup.body
            if body is not None:
                description_text = body.get_text("\n").strip() or None
                description_html_clean = str(body)
        posted_at = LinkedInScraper._parse_iso(card.get("posted_at_text"))
        return RawJob(
            source=JobSource.LINKEDIN,
            external_id=external_id,
            source_url=f"{LinkedInScraper._FALLBACK_VIEW_BASE}{external_id}",
            board=ApplicationBoard.LINKEDIN,
            url_type="external",
            company_name=str(company),
            position_title=str(title),
            location_raw=card.get("location"),
            description_html=description_html_clean,
            description_text=description_text,
            posted_at=posted_at,
            posted_at_text=card.get("posted_at_text"),
            raw_meta={"detail_endpoint": detail_url},
        )

    async def _scrape_rsshub(self, query: ScrapeQuery) -> AsyncIterator[RawJob]:
        # Plan 43 (`0.2.0.07a`): no slug substitution applies here. `base` comes
        # from `settings.scraper_rsshub_url` (env-only, operator-trust boundary);
        # `keywords` + `location` originate from env-loaded `Settings.linkedin_*`
        # and use `+` separators (URL-path shape, NOT slug shape). Trust boundary
        # = env; the `is_safe_destination(rsshub_url)` call below is the chokepoint.
        base = (settings.scraper_rsshub_url or "").rstrip("/")
        keywords = "+".join(query.keywords) if query.keywords else ""
        location = (query.location or "").replace(" ", "+")
        rsshub_url = f"{base}/linkedin/jobs/{keywords}/{location}".rstrip("/")
        safe, reason = is_safe_destination(rsshub_url)
        if not safe:
            self._errors.append(
                f"stage=fallback url={safe_url(rsshub_url)} kind=url_guard_blocked msg={reason}"
            )
            return
        try:
            xml = await self._client.fetch_html(rsshub_url)
        except Exception as exc:  # noqa: BLE001 — tier-1
            self._errors.append(
                f"stage=fallback url={safe_url(rsshub_url)} "
                f"kind=fallback_fetch_failure msg={safe_exc(exc)}"
            )
            return
        if not xml:
            return
        soup = BeautifulSoup(xml, "xml")
        yielded = 0
        for item in soup.select("item"):
            if yielded >= query.max_listings:
                return
            link = item.select_one("link")
            link_text = link.get_text(strip=True) if link else None
            if not link_text:
                continue
            m = _VIEW_HREF_RE.search(link_text) or re.search(r"/(\d+)\b", link_text)
            if not m:
                continue
            ext_id = m.group(1)
            title_el = item.select_one("title")
            desc_el = item.select_one("description")
            raw_job = RawJob(
                source=JobSource.LINKEDIN,
                external_id=ext_id,
                source_url=link_text,
                board=ApplicationBoard.LINKEDIN,
                url_type="external",
                company_name="Unknown Company",
                position_title=title_el.get_text(strip=True) if title_el else "Unknown Title",
                description_text=desc_el.get_text("\n").strip() if desc_el else None,
                raw_meta={"via": "rsshub"},
            )
            enriched = await self._maybe_enrich(raw_job)
            yielded += 1
            yield enriched

    @staticmethod
    def _parse_iso(value: object) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
