"""Scraper boundary DTOs — `RawJob` + `ScrapeQuery`.

Per docs/design/SCRAPER_BASE.md § D (graduated from plan 29 § D.2). Lives at
the scraper -> service boundary. Scraper subclasses fill the fields they can
from source HTML; `scraper_service.run_scraper` maps to `Job` via
`job_service.upsert_job(... raw=raw_job.model_dump(exclude_unset=True))`.

AI extraction (0.2.0.08) takes over for missing structured fields by
re-parsing `description_html` and overwriting `*_hint` values with
authoritative enum reads from the JD body.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from models import (
    ApplicationBoard,
    JobSource,
    RemotePolicy,
    SeniorityLevel,
    VisaRestriction,
)


class RawJob(BaseModel):
    """Scraper-emitted job payload before AI extraction + dedup.

    `extra="forbid"`: scraper authors who add fields that don't map to `Job`
    get a `ValidationError` at construction time. Forces an explicit add to
    `RawJob` (which forces an explicit `Job` field mapping) instead of
    silently passing through `raw_meta`.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    # Required: dedup keys + Job.upsert_job contract requirements
    source: JobSource
    external_id: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    board: ApplicationBoard
    url_type: str = "external"

    # Required: user-visible Job fields the scraper can fill
    company_name: str = Field(min_length=1)
    position_title: str = Field(min_length=1)

    # Optional structured fields; AI extraction refines or supplies if missing
    location_raw: str | None = None
    description_html: str | None = None
    description_text: str | None = None

    # Hints — scrapers fill when source data is unambiguous; AI extraction
    # overwrites if the hint is wrong or absent
    posted_at_text: str | None = None
    posted_at: datetime | None = None
    salary_raw: str | None = None
    remote_policy_hint: RemotePolicy | None = None
    visa_restriction_hint: VisaRestriction | None = None
    seniority_level_hint: SeniorityLevel | None = None

    # Source-specific extras kept in JSONB for diagnostics + audit. Soft cap
    # `< 4KB` per RawJob; runaway growth is a Phase 6 monitoring concern.
    raw_meta: dict[str, Any] = Field(default_factory=dict)


class ScrapeQuery(BaseModel):
    """Inputs to one scraper invocation.

    Per-scraper subclasses interpret as appropriate (LinkedIn: keywords +
    location; Greenhouse: company list; etc.). Conservative defaults so a
    bare `ScrapeQuery()` never spawns an unbounded scrape.
    """

    keywords: list[str] = Field(default_factory=list)
    location: str | None = None
    company_filter: list[str] | None = None
    max_listings: int = 200
    raw_meta: dict[str, Any] = Field(default_factory=dict)
