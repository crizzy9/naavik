"""Job entity — pre-application opportunities (scraped or manual).

Per DATA_MODEL.md § C `Job` + docs/design/JOB_MODEL.md (plan 27, 0.2.0.05).
`queue_state` flips to `applied` when an Application transitions to APPLIED.
`match_breakdown` is JSONB with tag → score mapping.

Pydantic API schemas (`JobFilter`, `JobRead`) live alongside the SQLModel
per `AGENTS.md § Code Style`. Co-locating keeps shape changes mechanically
coupled to the API view.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict
from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlmodel import Field, SQLModel

from ._common import utcnow
from .enums import (
    ApplicationBoard,
    JobQueueState,
    JobSource,
    RemotePolicy,
    SeniorityLevel,
    Tag,
    VisaRestriction,
)


class Job(SQLModel, table=True):
    __tablename__ = "job"
    __table_args__ = (
        CheckConstraint("score >= 0.0 AND score <= 1.0", name="ck_job_score_range"),
        CheckConstraint(
            "salary_min IS NULL OR salary_max IS NULL OR salary_min <= salary_max",
            name="ck_job_salary_min_le_max",
        ),
        Index("ix_job_user_queue", "user_id", "queue_state"),
        Index("ix_job_score_desc", "score"),
        Index("ix_job_found_at_desc", "found_at"),
        Index("ix_job_tags_gin", "tags", postgresql_using="gin"),
        Index(
            "ix_job_user_url_unique_alive",
            "user_id",
            "url",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
        # Primary dedup constraint per plan 27 § D.3.
        Index(
            "ix_job_user_source_external_id_unique_alive",
            "user_id",
            "source",
            "external_id",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
        # Tier-3 fuzzy dedup candidate-narrowing index (plan 34 § D.6).
        # GIN trigram on lower(company); declared in alembic 0006 because
        # SQLModel can't natively express the expression-index + opclass.
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", ondelete="CASCADE", index=True)

    source: JobSource
    board: ApplicationBoard
    # Per-source stable identifier — `linkedin_job_id`, `greenhouse_internal_id`,
    # `lever_postingId`, etc. MANUAL source synthesizes `manual-<uuid7>`.
    external_id: str
    url: str = Field(index=True)
    url_type: str

    company: str
    role: str
    team: str | None = None
    location: str | None = None
    remote_policy: RemotePolicy = Field(default=RemotePolicy.UNKNOWN)
    seniority_level: SeniorityLevel | None = None

    posted_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    # Raw posted-date string from the scraper before normalization
    # (e.g. "Posted 3 days ago"). Diagnostics aid only.
    posted_at_text: str | None = None
    found_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )

    description: str
    description_html: str | None = None
    description_extracted_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    description_extraction_model: str | None = None
    criteria: list[str] = Field(
        default_factory=list,
        sa_column=Column(ARRAY(String), nullable=False, server_default="{}"),
    )
    skills_required: list[str] = Field(
        default_factory=list,
        sa_column=Column(ARRAY(String), nullable=False, server_default="{}"),
    )
    visa_restrictions: VisaRestriction = Field(default=VisaRestriction.NOT_MENTIONED)

    salary_min: int | None = None
    salary_max: int | None = None
    equity_pct: float | None = None

    score: float = Field(default=0.0)
    score_explanation: str | None = None
    match_breakdown: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
    )

    queue_state: JobQueueState = Field(default=JobQueueState.UNSWIPED)
    tags: list[str] = Field(
        default_factory=list,
        sa_column=Column(ARRAY(String), nullable=False, server_default="{}"),
    )

    warm_intro_contact_id: int | None = Field(
        default=None,
        foreign_key="contact.id",
        ondelete="SET NULL",
    )
    # FK to the JobScrapeRun row that most recently touched this Job.
    # NULL until the first scrape-run write lands (plan 27 § D.2).
    last_scrape_run_id: int | None = Field(
        default=None,
        foreign_key="job_scrape_run.id",
        ondelete="SET NULL",
    )
    # Tier-3 fuzzy dedup link (plan 34 § D.3). Self-FK; ON DELETE SET NULL
    # so archiving the canonical Job re-surfaces shadowed rows in Discover.
    duplicate_of_id: int | None = Field(
        default=None,
        sa_column=Column(
            Integer,
            ForeignKey("job.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )
    raw_meta: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
    )

    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    deleted_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )


# ── Pydantic API schemas (plan 27 § D.8) ─────────────────────────────────


class JobFilter(BaseModel):
    """Query-param filter for `/api/v1/jobs` (Phase 2.0.11 surface)."""

    # Free-text search over company + role (ILIKE) — Tracking · Jobs library.
    q: str | None = None
    company: str | None = None
    source: JobSource | None = None
    board: ApplicationBoard | None = None
    visa: VisaRestriction | None = None
    remote_only: bool = False
    seniority: SeniorityLevel | None = None
    queue_state: JobQueueState | None = None
    score_min: float = 0.0
    score_max: float = 1.0
    tag: Tag | None = None
    posted_within_days: int | None = None
    # Diagnostic mode (operator Scrapes panel). Default hides duplicates so
    # Discover never surfaces a tier-3 shadow row (plan 34 § D.3).
    include_duplicates: bool = False


def _validate_job_url(value: str) -> str:
    """Reject any scheme that's renderable as an href but not navigable as a
    real link — the `javascript:` / `data:` / `file:` family. http / https
    cover real ATS + company pages; `manual://` is the synthetic-id scheme
    for URL-less manual entries (see `ui.routes.jobs.post_job_manual`).
    Closes hacker PR #153 HIGH-2 (stored-XSS via slide-over `<a href>`).
    """
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("url required")
    lower = cleaned.lower()
    if lower.startswith(("http://", "https://", "manual://")):
        return cleaned
    scheme = cleaned.split(":", 1)[0] if ":" in cleaned else cleaned
    raise ValueError(f"unsupported URL scheme: {scheme}")


JobUrl = Annotated[str, AfterValidator(_validate_job_url)]


class JobCreate(BaseModel):
    """API input for manual job creation (`+ Add by URL`)."""

    url: JobUrl
    board: ApplicationBoard
    company: str
    role: str
    description: str
    team: str | None = None
    location: str | None = None
    remote_policy: RemotePolicy = RemotePolicy.UNKNOWN
    seniority_level: SeniorityLevel | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    visa_restrictions: VisaRestriction = VisaRestriction.NOT_MENTIONED


class JobUpdate(BaseModel):
    """API input for partial Job updates."""

    company: str | None = None
    role: str | None = None
    team: str | None = None
    location: str | None = None
    remote_policy: RemotePolicy | None = None
    seniority_level: SeniorityLevel | None = None
    description: str | None = None
    visa_restrictions: VisaRestriction | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    queue_state: JobQueueState | None = None
    score: float | None = None
    score_explanation: str | None = None


class JobRead(BaseModel):
    """API output for `/api/v1/jobs/{id}` (Phase 2.0.11 surface).

    `raw_meta` is intentionally omitted (plan 46 / 0.2.0.11c):
    scraper-controlled JSONB may carry vendor noise / unexpected fields
    and is not part of the public API contract. Defense-in-depth on top
    of the owner-only IDOR gate.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    source: JobSource
    board: ApplicationBoard
    external_id: str
    url: str
    url_type: str
    company: str
    role: str
    team: str | None
    location: str | None
    remote_policy: RemotePolicy
    seniority_level: SeniorityLevel | None
    posted_at: datetime | None
    posted_at_text: str | None
    found_at: datetime
    description: str
    description_extracted_at: datetime | None
    description_extraction_model: str | None
    criteria: list[str]
    skills_required: list[str]
    visa_restrictions: VisaRestriction
    salary_min: int | None
    salary_max: int | None
    equity_pct: float | None
    score: float
    score_explanation: str | None
    match_breakdown: dict
    queue_state: JobQueueState
    tags: list[str]
    warm_intro_contact_id: int | None
    last_scrape_run_id: int | None
    duplicate_of_id: int | None
    created_at: datetime
    updated_at: datetime
