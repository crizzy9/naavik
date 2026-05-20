"""Workday job-board scraper.

Per docs/design/SCRAPER_SITES.md § Workday (graduated from plan 33 § D.6.3).

Workday is per-tenant — each customer (Salesforce, Adobe, Citi, etc.) has
their own ``<tenant>.wd1.myworkdayjobs.com`` (or ``.wd3.``) subdomain. The
scraper iterates ``Settings.workday_companies`` (`list[str]`) where each
entry is `"<tenant>/<site>"` (e.g. `"salesforce/External"`,
`"adobe/Adobe_Careers"`).

URL composition:
- List: ``https://{tenant}.wd1.myworkdayjobs.com/{site}``
- Detail: ``https://{tenant}.wd1.myworkdayjobs.com/{site}/job/{loc}/{title}_{R-XXXXXX}``

External-ID rule: requisition ID (e.g. ``R-12345`` or ``JR12345``)
extracted from the detail-page URL path. Regex:
``/job/[^/]+/[^/]+_([A-Z]+[-_]?\\d+)``.

Rate limit: 2 req/min (1 req per 30s) per BACKEND.md § J.2. Random delay
20-40s. Conservative — Workday WAF is aggressive.
"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from config import settings
from models import ApplicationBoard, JobSource
from scraper.redaction import safe_exc, safe_url
from scraper.sites._base_site import _BaseSiteScraper
from scraper.types import RawJob, ScrapeQuery
from scraper.url_guard import is_safe_destination

log = logging.getLogger(__name__)

_REQ_ID_RE = re.compile(r"/job/[^/]+/[^/]+_([A-Z]+[-_]?\d+)")


class WorkdayScraper(_BaseSiteScraper):
    """Workday per-tenant scraper."""

    source = JobSource.WORKDAY
    board = ApplicationBoard.WORKDAY
    rate_limit_per_minute = 2
    random_delay_seconds = (20.0, 40.0)

    _LIST_TEMPLATE = "https://{tenant}.wd1.myworkdayjobs.com/{site}"

    async def scrape(self, query: ScrapeQuery) -> AsyncIterator[RawJob]:
        tenants = self._resolve_tenants(query)
        if not tenants:
            log.info("workday: no tenants configured; nothing to scrape")
            return

        yielded = 0
        for tenant_spec in tenants:
            tenant, site = self._parse_tenant_spec(tenant_spec)
            if not tenant or not site:
                self._errors.append(
                    f"stage=list url=<workday-spec> kind=invalid_tenant_spec msg={tenant_spec!r}"
                )
                continue
            list_url = self._compose_url(
                self._LIST_TEMPLATE, stage="list", tenant=tenant, site=site
            )
            if list_url is None:
                continue
            safe, reason = is_safe_destination(list_url)
            if not safe:
                self._errors.append(
                    f"stage=list url={safe_url(list_url)} kind=url_guard_blocked msg={reason}"
                )
                continue

            try:
                listing_html = await self._client.fetch_html(list_url)
            except Exception as exc:  # noqa: BLE001 — tier-1
                self._errors.append(
                    f"stage=list url={safe_url(list_url)} "
                    f"kind=list_fetch_failure msg={safe_exc(exc)}"
                )
                continue

            cards = self._parse_listing_cards(listing_html, tenant=tenant, site=site)
            for card in cards:
                if yielded >= query.max_listings:
                    return
                detail_url = card.get("detail_url")
                if not detail_url:
                    continue
                safe_d, reason_d = is_safe_destination(detail_url)
                if not safe_d:
                    self._errors.append(
                        f"stage=detail url={safe_url(detail_url)} "
                        f"kind=url_guard_blocked msg={reason_d}"
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
                    tenant=tenant,
                    card=card,
                    detail_url=detail_url,
                    detail_html=detail_html,
                )
                if raw_job is None:
                    continue
                enriched = await self._maybe_enrich(raw_job)
                yielded += 1
                yield enriched

    def _resolve_tenants(self, query: ScrapeQuery) -> list[str]:
        if query.company_filter:
            return [c for c in query.company_filter if c]
        return list(settings.workday_companies or [])

    @staticmethod
    def _parse_tenant_spec(spec: str) -> tuple[str | None, str | None]:
        """Accept `"tenant/site"` or `"tenant"` (site defaults to `"External"`)."""
        if not spec:
            return None, None
        if "/" in spec:
            tenant, site = spec.split("/", 1)
            return tenant.strip() or None, site.strip() or None
        return spec.strip() or None, "External"

    @staticmethod
    def _parse_listing_cards(
        html: str | None, *, tenant: str, site: str
    ) -> list[dict[str, str | None]]:
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")
        cards: list[dict[str, str | None]] = []
        # Workday's listing DOM uses `data-automation-id="jobTitle"` anchors.
        for anchor in soup.select('a[data-automation-id="jobTitle"]'):
            href = anchor.get("href", "")
            if not href:
                continue
            detail_url = WorkdayScraper._absolutize(href, tenant=tenant, site=site)
            req_match = _REQ_ID_RE.search(detail_url)
            if not req_match:
                continue
            req_id = req_match.group(1)
            title = anchor.get_text(strip=True)
            container = anchor.find_parent("li") or anchor.parent
            location_el = (
                container.select_one('div[data-automation-id="locations"]')
                if container is not None
                else None
            )
            location = location_el.get_text(" ", strip=True) if location_el else None
            cards.append(
                {
                    "external_id": req_id,
                    "title": title,
                    "location": location,
                    "detail_url": detail_url,
                }
            )
        return cards

    @staticmethod
    def _absolutize(href: str, *, tenant: str, site: str) -> str:
        if href.startswith("http://") or href.startswith("https://"):
            return href
        if href.startswith("/"):
            return f"https://{tenant}.wd1.myworkdayjobs.com{href}"
        return f"https://{tenant}.wd1.myworkdayjobs.com/{site}/{href}"

    @staticmethod
    def _build_raw_job(
        *,
        tenant: str,
        card: dict[str, str | None],
        detail_url: str,
        detail_html: str | None,
    ) -> RawJob | None:
        external_id = card.get("external_id")
        title = card.get("title")
        if not external_id or not title:
            return None
        description_text = None
        description_html_clean = None
        if detail_html:
            soup = BeautifulSoup(detail_html, "html.parser")
            body = (
                soup.select_one('div[data-automation-id="jobPostingDescription"]')
                or soup.select_one('div[data-automation-id="jobDescription"]')
                or soup.body
            )
            if body is not None:
                description_text = body.get_text("\n").strip() or None
                description_html_clean = str(body)
        # Company name derived from tenant; production cron may override via
        # raw_meta if a friendlier display name is configured.
        return RawJob(
            source=JobSource.WORKDAY,
            external_id=external_id,
            source_url=detail_url,
            board=ApplicationBoard.WORKDAY,
            url_type="external",
            company_name=tenant,
            position_title=str(title),
            location_raw=card.get("location"),
            description_html=description_html_clean,
            description_text=description_text,
            raw_meta={
                "tenant": tenant,
                "host": urlsplit(detail_url).hostname,
            },
        )
