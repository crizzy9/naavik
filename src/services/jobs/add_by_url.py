"""Add-by-URL pipeline — plan 95 § 3.7 (slice 95j).

The headless posting-URL flow (SSRF guard → Crawl4AI fetch → LLM
`extract_job` enrichment) extracted from `email.inference` so both callers
share ONE pipeline:

- email receipts (headless: fetch + upsert immediately), and
- the URL-first manual modal (fetch → EDITABLE PREVIEW → human confirms
  before anything persists — bad extractions die at the preview).
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass

from sqlmodel.ext.asyncio.session import AsyncSession

from models.enums import ApplicationBoard, JobSource

log = logging.getLogger(__name__)


class AddByUrlError(Exception):
    """Guarded/failed fetch — callers surface the message, never a 500."""


@dataclass(slots=True)
class ParsedPosting:
    """LLM-extracted posting fields for the editable preview (§ 3.7 B)."""

    url: str
    company: str
    role: str
    location: str | None
    description: str
    salary_min: int | None
    salary_max: int | None
    board: str


async def fetch_and_extract(
    session: AsyncSession,
    *,
    user_id: int,
    url: str,
    source: JobSource = JobSource.MANUAL,
    board: ApplicationBoard = ApplicationBoard.MANUAL,
    url_type: str = "external",
    external_prefix: str = "manual",
):
    """Guarded fetch + LLM enrichment. Returns an enriched `RawJob` (NOT
    persisted). Raises AddByUrlError on guard rejection / empty fetch."""
    from llm import LLMProviderError, get_provider
    from scraper.crawl4ai_client import Crawl4AIClient
    from scraper.types import RawJob
    from scraper.url_guard import is_safe_destination
    from services import settings as settings_service
    from services.jobs.extractor import enrich_raw_job

    safe, reason = is_safe_destination(url)
    if not safe:
        log.info("add-by-url rejected (%s): %s", reason, url)
        raise AddByUrlError("That URL can't be fetched from here.")
    client = Crawl4AIClient(rate_limit_per_minute=30.0, random_delay_seconds=(0.0, 0.1))
    html = await client.fetch_html(url)
    if not html:
        raise AddByUrlError(
            "Couldn't fetch the posting (login wall / JS-only page?) — type the fields instead."
        )
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    page_title = (title_match.group(1).strip()[:160] if title_match else "") or "Unknown role"
    seed_role, seed_company = page_title, "Unknown"
    for sep in (" | ", " – ", " — ", " - ", " · "):
        if sep in page_title:
            left, right = page_title.split(sep, 1)
            seed_role = left.strip() or "Unknown role"
            seed_company = right.strip() or "Unknown"
            break
    external_id = f"{external_prefix}-{hashlib.sha1(url.encode()).hexdigest()[:12]}"
    raw_job = RawJob(
        source=source,
        external_id=external_id,
        source_url=url,
        board=board,
        url_type=url_type,
        company_name=seed_company,
        position_title=seed_role,
        description_html=html,
    )
    settings = await settings_service.get_or_create(session, user_id=user_id)
    try:
        provider = get_provider(settings)
        raw_job = await enrich_raw_job(session, user_id=user_id, provider=provider, raw_job=raw_job)
    except LLMProviderError:
        # No provider: the title-seeded fields still make a usable preview.
        pass
    return raw_job


async def parse_posting(session: AsyncSession, *, user_id: int, url: str) -> ParsedPosting:
    """The manual-modal preview step — nothing persists here (§ 3.7 B)."""
    raw = await fetch_and_extract(session, user_id=user_id, url=url)
    payload = raw.to_upsert_payload()
    description = payload.get("description") or ""
    return ParsedPosting(
        url=url,
        company=(payload.get("company") or "Unknown").strip()[:160],
        role=(payload.get("role") or "Unknown role").strip()[:200],
        location=(payload.get("location") or None),
        description=description[:8000],
        salary_min=payload.get("salary_min"),
        salary_max=payload.get("salary_max"),
        board=str(payload.get("board") or ApplicationBoard.MANUAL.value),
    )
