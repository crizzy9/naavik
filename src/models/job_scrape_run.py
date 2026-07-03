"""JobScrapeRun entity — one row per scraper invocation.

Per plan 27 § D.2 + docs/design/JOB_MODEL.md. Scrape-side observability:
each scraper invocation persists `(source, started_at, finished_at, status,
requests_made, listings_returned, new_jobs, updated_jobs, errors, ...)` so
the dedup logic (0.2.0.09), rate limiter (0.2.0.13), and operator UI
(future Scrapes panel) have something to read.

Distinct from `AppEvent` (which is per-Application history). `Job.last_scrape_run_id`
FKs back here for the "this listing last refreshed via LinkedIn 2h ago" UI.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import CheckConstraint, Column, DateTime, Index, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlmodel import Field, SQLModel

from ._common import utcnow
from .enums import JobScrapeStatus, JobSource


class JobScrapeRun(SQLModel, table=True):
    __tablename__ = "job_scrape_run"
    __table_args__ = (
        CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name="ck_job_scrape_run_finish_after_start",
        ),
        CheckConstraint(
            "requests_made >= 0 AND listings_returned >= 0 AND new_jobs >= 0 AND updated_jobs >= 0",
            name="ck_job_scrape_run_counters_nonneg",
        ),
        Index("ix_job_scrape_run_source_started", "source", "started_at"),
        Index("ix_job_scrape_run_user_status_started", "user_id", "status", "started_at"),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", ondelete="CASCADE", index=True)

    source: JobSource
    status: JobScrapeStatus
    # "cron" | "manual" | "test" | "migration" — free-form per plan 27 § D.2.
    triggered_by: str

    started_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )
    finished_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )

    requests_made: int = Field(default=0)
    listings_returned: int = Field(default=0)
    new_jobs: int = Field(default=0)
    updated_jobs: int = Field(default=0)
    # Listings recognized from the library BEFORE the detail fetch — the
    # known-ID skip's receipt (2026-07 volume rework).
    duplicates_skipped: int = Field(default=0)

    # Bounded by anti-detection budget; typical 0-5 entries per run.
    # Plain strings (not JSONB) — operator-grep-able in logs / admin views.
    errors: list[str] = Field(
        default_factory=list,
        sa_column=Column(ARRAY(String), nullable=False, server_default="{}"),
    )

    duration_ms: int | None = None
    raw_meta: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
    )

    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


# ── Pydantic API schemas (plan 27 § D.8) ─────────────────────────────────


class JobScrapeRunRead(BaseModel):
    """API output for the future `/api/v1/scrape-runs` surface."""

    id: int
    user_id: int
    source: JobSource
    status: JobScrapeStatus
    triggered_by: str
    started_at: datetime
    finished_at: datetime | None
    requests_made: int
    listings_returned: int
    new_jobs: int
    updated_jobs: int
    errors: list[str]
    duration_ms: int | None
    raw_meta: dict
    created_at: datetime
