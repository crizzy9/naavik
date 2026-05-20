"""Indeed job-board scraper.

Per docs/design/SCRAPER_SITES.md § Indeed (graduated from plan 33 § D.6.5).

Indeed is aggressively anti-bot (Cloudflare WAF + fingerprinting). Crawl4AI
stealth is the front-line defense. Plan 38 (`0.2.0.13`) shipped the
`UndetectedAdapter` wiring + per-source telemetry; the class-attr stays
`use_undetected_adapter = False` until `0.2.0.13c` flips it on after
observed 403-rate exceeds ~5%.

URL composition:
- Search: ``https://www.indeed.com/jobs?q={kw}&l={loc}`` (HTML listing)
- Detail: ``https://www.indeed.com/viewjob?jk={jk}``

External-ID rule: ``jk`` query-param from listing-card link. Regex
``[?&]jk=([a-f0-9]+)``.

Rate limit: 2 req/min (1 req per 30s) per BACKEND.md § J.2. Random delay
20-40s. Per-source operator overrides via `Settings.scraper_rate_limits`
(plan 38). If 403-rate exceeds 5% on real runs, file `0.2.0.13c` follow-up.
"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from models import ApplicationBoard, JobSource
from scraper.redaction import safe_exc, safe_url
from scraper.sites._base_site import _BaseSiteScraper
from scraper.types import RawJob, ScrapeQuery
from scraper.url_guard import is_safe_destination

log = logging.getLogger(__name__)

_JK_RE = re.compile(r"[?&]jk=([a-f0-9]+)")


class IndeedScraper(_BaseSiteScraper):
    """Indeed HTML scraper."""

    source = JobSource.INDEED
    board = ApplicationBoard.INDEED
    rate_limit_per_minute = 2
    random_delay_seconds = (20.0, 40.0)

    _LIST_BASE = "https://www.indeed.com/jobs"
    _DETAIL_BASE = "https://www.indeed.com/viewjob"

    async def scrape(self, query: ScrapeQuery) -> AsyncIterator[RawJob]:
        list_url = self._compose_listing_url(query)
        safe, reason = is_safe_destination(list_url)
        if not safe:
            self._errors.append(
                f"stage=list url={safe_url(list_url)} kind=url_guard_blocked msg={reason}"
            )
            return

        try:
            listing_html = await self._client.fetch_html(list_url)
        except Exception as exc:  # noqa: BLE001 — tier-1
            self._errors.append(
                f"stage=list url={safe_url(list_url)} kind=list_fetch_failure msg={safe_exc(exc)}"
            )
            return
        if not listing_html:
            return

        cards = self._parse_listing_cards(listing_html)
        yielded = 0
        for card in cards:
            if yielded >= query.max_listings:
                return
            jk = card.get("jk")
            if not jk:
                continue
            detail_url = f"{self._DETAIL_BASE}?jk={jk}"
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
                jk=jk, detail_url=detail_url, card=card, detail_html=detail_html
            )
            if raw_job is None:
                continue
            enriched = await self._maybe_enrich(raw_job)
            yielded += 1
            yield enriched

    def _compose_listing_url(self, query: ScrapeQuery) -> str:
        kw = " ".join(query.keywords) if query.keywords else ""
        loc = query.location or ""
        return f"{self._LIST_BASE}?q={quote_plus(kw)}&l={quote_plus(loc)}"

    @staticmethod
    def _parse_listing_cards(html: str) -> list[dict[str, str | None]]:
        soup = BeautifulSoup(html, "html.parser")
        cards: list[dict[str, str | None]] = []
        # Indeed mostly uses `.job_seen_beacon`; older `.jobsearch-SerpJobCard`
        # still appears in some regions. Try both.
        selectors = [".job_seen_beacon", ".jobsearch-SerpJobCard", "div.result"]
        for sel in selectors:
            for card_el in soup.select(sel):
                jk = IndeedScraper._extract_jk(card_el)
                if not jk:
                    continue
                title_el = card_el.select_one("h2 a span") or card_el.select_one("h2 a")
                company_el = card_el.select_one(
                    '[data-testid="company-name"]'
                ) or card_el.select_one(".companyName")
                location_el = card_el.select_one(
                    '[data-testid="text-location"]'
                ) or card_el.select_one(".companyLocation")
                cards.append(
                    {
                        "jk": jk,
                        "title": title_el.get_text(strip=True) if title_el else None,
                        "company": company_el.get_text(strip=True) if company_el else None,
                        "location": location_el.get_text(strip=True) if location_el else None,
                    }
                )
            if cards:
                break
        return cards

    @staticmethod
    def _extract_jk(card_el) -> str | None:  # type: ignore[no-untyped-def]
        if hasattr(card_el, "get"):
            attr_jk = card_el.get("data-jk")
            if attr_jk:
                return str(attr_jk)
        for a in card_el.select("a[href]"):
            href = str(a.get("href", ""))
            m = _JK_RE.search(href)
            if m:
                return m.group(1)
        return None

    @staticmethod
    def _build_raw_job(
        *,
        jk: str,
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
            body = soup.select_one("#jobDescriptionText") or soup.body
            if body is not None:
                description_text = body.get_text("\n").strip() or None
                description_html_clean = str(body)
        return RawJob(
            source=JobSource.INDEED,
            external_id=jk,
            source_url=detail_url,
            board=ApplicationBoard.INDEED,
            url_type="external",
            company_name=str(company),
            position_title=str(title),
            location_raw=card.get("location"),
            description_html=description_html_clean,
            description_text=description_text,
            raw_meta={"jk": jk},
        )
