"""Scraper boundary DTOs — `RawJob` + `ScrapeQuery`.

Per docs/design/SCRAPER_BASE.md § D (graduated from plan 29 § D.2). Lives at
the scraper -> service boundary. Scraper subclasses fill the fields they can
from source HTML; `scraper_service.run_scraper` maps to `Job` via
`job_service.upsert_job(... raw=raw_job.to_upsert_payload())`.

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

    def to_upsert_payload(self) -> dict[str, Any]:
        """Map `RawJob` field names onto `job_service.upsert_job`'s `raw` dict.

        `_JOB_CREATE_FIELDS` in `job_service` is keyed by `Job` column names
        (`url`, `company`, `role`, `description`, `remote_policy`, ...), not
        `RawJob` names (`source_url`, `company_name`, `position_title`,
        `description_text`, `remote_policy_hint`, ...). `model_dump()` alone
        produces the wrong shape and `_create_payload` silently drops every
        unmatched key, so the resulting `Job(...)` is missing NOT-NULL fields
        and only fails when Postgres enforces the constraint — which the
        in-memory test session bypasses.

        Hints map into the matching `Job` column verbatim (e.g.
        `remote_policy_hint` -> `Job.remote_policy`); AI extraction
        (`0.2.0.08`) overwrites with the authoritative read from the JD body.
        `salary_raw` has no `Job` counterpart — preserved under `raw_meta`
        for the same AI extraction step to parse.
        """
        raw_meta = dict(self.raw_meta)
        if self.salary_raw is not None:
            raw_meta.setdefault("salary_raw", self.salary_raw)

        # Scorer-required arrays + salary bounds + extraction attribution are
        # merged into raw_meta by job_extractor; promote them to real Job
        # columns here. Leaving them nested made every scraped job land with
        # Job.tags == [] → tag overlap 0.0 → permanently below the tag floor.
        promoted: dict[str, Any] = {}
        for key in (
            "tags",
            "skills_required",
            "criteria",
            "salary_min",
            "salary_max",
            "description_extraction_model",
        ):
            if key in raw_meta:
                promoted[key] = raw_meta.pop(key)

        payload: dict[str, Any] = {
            "board": self.board,
            "url": self.source_url,
            "url_type": self.url_type,
            "company": self.company_name,
            "role": self.position_title,
            "location": self.location_raw,
            "description": self.description_text or "",
            "description_html": self.description_html,
            "posted_at": self.posted_at,
            "posted_at_text": self.posted_at_text,
            "raw_meta": raw_meta,
        }
        payload.update(promoted)
        if self.remote_policy_hint is not None:
            payload["remote_policy"] = self.remote_policy_hint
        if self.visa_restriction_hint is not None:
            payload["visa_restrictions"] = self.visa_restriction_hint
        if self.seniority_level_hint is not None:
            payload["seniority_level"] = self.seniority_level_hint
        return payload


class ScrapeQuery(BaseModel):
    """Inputs to one scraper invocation.

    Per-scraper subclasses interpret as appropriate (LinkedIn: keywords +
    location; Greenhouse: company list; etc.). Conservative defaults so a
    bare `ScrapeQuery()` never spawns an unbounded scrape.
    """

    keywords: list[str] = Field(default_factory=list)
    location: str | None = None
    company_filter: list[str] | None = None
    max_listings: int = Field(default=200, ge=1, le=10_000)
    raw_meta: dict[str, Any] = Field(default_factory=dict)
