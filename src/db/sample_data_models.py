"""Pydantic-only mirror of the SQLModel entities defined in DATA_MODEL.md § C.

Plan 09 lives entirely on these classes (sample-data fixtures + page handlers).
Plan 10 Wave 4 introduces `src/models/*.py` as `SQLModel(table=True)` with
identical field names; the eventual swap is mechanical.

Critical: these are `BaseModel`, NOT `SQLModel(table=True)`. We deliberately
avoid the SQLAlchemy registry until Wave 4 so plan 09 is dependency-free at
import time.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from models.enums import (
    AppEventKind,
    ApplicationBoard,
    ApplicationStatus,
    AtsLoginStatus,
    BulletSelectionOverride,
    ClosedReason,
    ContactType,
    DeploymentMode,
    DisabilityStatus,
    DocsState,
    EmailClassification,
    Gender,
    GeneratedDocumentKind,
    JobQueueState,
    JobScrapeStatus,
    JobSource,
    LLMProvider,
    OutreachIntent,
    OutreachStatus,
    Race,
    RecruiterState,
    ReferralState,
    RelocateOpenness,
    RemotePolicy,
    ScreenerAnswerSource,
    ScreenerQuestionType,
    SeniorityLevel,
    Tag,
    VeteranStatus,
    VisaRestriction,
    VisaSponsorship,
    WorkAuthorization,
)


class _Base(BaseModel):
    """Shared config: assignment validation OFF (in-memory mutation OK)."""

    model_config = ConfigDict(arbitrary_types_allowed=True, validate_assignment=False)


# ── Identity ─────────────────────────────────────────────────────────────


class User(_Base):
    id: int
    email: str
    password_hash: str
    is_active: bool = True
    is_admin: bool = False
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None
    deleted_at: datetime | None = None


class Profile(_Base):
    id: int
    user_id: int

    full_name: str
    headline: str
    current_company: str | None = None
    location: str | None = None
    email: str
    phone: str | None = None
    portfolio_url: str | None = None
    github_handle: str | None = None
    linkedin_handle: str | None = None
    open_to_opportunities: bool = True

    summary_full: str | None = None
    summary_short: str | None = None

    work_authorization: WorkAuthorization | None = None
    visa_sponsorship_needed: VisaSponsorship | None = None
    willing_to_relocate: RelocateOpenness | None = None
    notice_period_days: int | None = None
    salary_expectation_usd: int | None = None
    earliest_start: datetime | None = None
    veteran_status: VeteranStatus | None = None
    disability_status: DisabilityStatus | None = None
    race_ethnicity: Race | None = None
    gender_identity: Gender | None = None

    cover_letter_base: dict[str, Any] | None = None

    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


# ── Resume substrate ─────────────────────────────────────────────────────


class Experience(_Base):
    id: int
    profile_id: int
    company: str
    title: str
    team: str | None = None
    location: str | None = None
    start_date: datetime
    end_date: datetime | None = None
    order_index: int = 0
    summary_short: str | None = None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class Bullet(_Base):
    id: int
    experience_id: int
    order_index: int = 0
    text: str
    tags: list[Tag] = Field(default_factory=list)
    selection_override: BulletSelectionOverride | None = None
    edited_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class Skill(_Base):
    id: int
    profile_id: int
    category: str
    items: list[str] = Field(default_factory=list)
    order_index: int = 0
    created_at: datetime
    updated_at: datetime


class Education(_Base):
    id: int
    profile_id: int
    institution: str
    school: str | None = None
    location: str | None = None
    degree: str
    start_date: datetime
    end_date: datetime | None = None
    gpa: str | None = None
    courses: list[str] = Field(default_factory=list)
    order_index: int = 0
    created_at: datetime
    updated_at: datetime


class Project(_Base):
    id: int
    profile_id: int
    title: str
    date: datetime | None = None
    text: str
    tags: list[Tag] = Field(default_factory=list)
    portfolio_slug: str | None = None
    link: str | None = None
    order_index: int = 0
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class Certification(_Base):
    id: int
    profile_id: int
    title: str
    issuer: str
    date: datetime | None = None
    description: str | None = None
    order_index: int = 0
    created_at: datetime
    updated_at: datetime


# ── Discovery + applications ─────────────────────────────────────────────


class Job(_Base):
    id: int
    user_id: int
    source: JobSource
    board: ApplicationBoard
    external_id: str
    url: str
    url_type: str

    company: str
    role: str
    team: str | None = None
    location: str | None = None
    remote_policy: RemotePolicy = RemotePolicy.UNKNOWN
    seniority_level: SeniorityLevel | None = None

    posted_at: datetime | None = None
    posted_at_text: str | None = None
    found_at: datetime

    description: str
    description_html: str | None = None
    description_extracted_at: datetime | None = None
    description_extraction_model: str | None = None
    criteria: list[str] = Field(default_factory=list)
    skills_required: list[str] = Field(default_factory=list)
    visa_restrictions: VisaRestriction = VisaRestriction.NOT_MENTIONED

    salary_min: int | None = None
    salary_max: int | None = None
    equity_pct: float | None = None

    score: float = 0.0
    score_explanation: str | None = None
    match_breakdown: dict[str, float] = Field(default_factory=dict)

    queue_state: JobQueueState = JobQueueState.UNSWIPED
    tags: list[Tag] = Field(default_factory=list)

    warm_intro_contact_id: int | None = None
    last_scrape_run_id: int | None = None
    raw_meta: dict[str, Any] = Field(default_factory=dict)

    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class JobScrapeRun(_Base):
    id: int
    user_id: int
    source: JobSource
    status: JobScrapeStatus
    triggered_by: str
    started_at: datetime
    finished_at: datetime | None = None
    requests_made: int = 0
    listings_returned: int = 0
    new_jobs: int = 0
    updated_jobs: int = 0
    errors: list[str] = Field(default_factory=list)
    duration_ms: int | None = None
    raw_meta: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class Application(_Base):
    id: int
    user_id: int
    job_id: int | None = None

    company: str
    role: str
    team: str | None = None
    location: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    equity_pct: float | None = None

    applied_at: datetime | None = None
    board: ApplicationBoard | None = None
    external_url: str | None = None

    status: ApplicationStatus = ApplicationStatus.DRAFT
    closed_reason: ClosedReason | None = None

    docs_state: DocsState = DocsState.NONE
    referral_state: ReferralState = ReferralState.NONE
    recruiter_state: RecruiterState = RecruiterState.NONE

    submission_artifacts: dict[str, Any] | None = None

    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    notes: str | None = None


# ── Outreach + email ─────────────────────────────────────────────────────


class Contact(_Base):
    id: int
    user_id: int
    type: ContactType
    name: str
    title: str | None = None
    company: str
    linkedin_url: str | None = None
    linkedin_id: str | None = None
    linkedin_degree: str | None = None
    email: str | None = None
    relationship: str | None = None
    source: str | None = None
    notes: str | None = None
    last_touch_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class ContactApplicationLink(_Base):
    id: int
    application_id: int
    contact_id: int
    referral_state: ReferralState = ReferralState.NONE
    introduced_at: datetime | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class OutreachMessage(_Base):
    id: int
    user_id: int
    contact_id: int
    application_id: int | None = None

    intent: OutreachIntent
    channel: str  # "linkedin_dm" | "email"
    subject: str | None = None
    body: str

    status: OutreachStatus = OutreachStatus.DRAFT
    sent_at: datetime | None = None
    opened_at: datetime | None = None
    replied_at: datetime | None = None
    response_summary: str | None = None

    ai_generated: bool = False
    human_edited: bool = False
    drafted_by_model: str | None = None
    linkedin_message_id: str | None = None

    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class EmailThread(_Base):
    id: int
    user_id: int
    application_id: int | None = None
    contact_id: int | None = None

    provider: str  # "gmail" | "outlook" | "imap"
    thread_id_external: str
    subject: str
    classification: EmailClassification
    auto_classified: bool = True
    manually_verified: bool = False

    latest_message_at: datetime
    message_count: int = 0
    messages: list[dict[str, Any]] = Field(default_factory=list)

    created_at: datetime
    updated_at: datetime


# ── Timeline + artifacts ─────────────────────────────────────────────────


class AppEvent(_Base):
    id: int
    user_id: int
    application_id: int | None = None
    kind: AppEventKind
    occurred_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)
    actor: str | None = None
    created_at: datetime


class GeneratedDocument(_Base):
    id: int
    application_id: int
    kind: GeneratedDocumentKind
    path: str
    byte_size: int
    page_count: int | None = None
    compiled_at: datetime
    model: str | None = None
    cost_usd: float | None = None
    token_count: int | None = None
    error: str | None = None
    bullet_selection: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class ApplicationScreenerAnswer(_Base):
    id: int
    application_id: int

    question_text: str
    question_fingerprint: str
    question_type: ScreenerQuestionType
    choices: list[str] | None = None
    required: bool = True
    order_index: int = 0

    answer: str | None = None
    source: ScreenerAnswerSource = ScreenerAnswerSource.DRAFTED
    drafted_by_model: str | None = None
    reviewed_at: datetime | None = None

    created_at: datetime
    updated_at: datetime


# ── Config ────────────────────────────────────────────────────────────────


class ATSCredential(_Base):
    id: int
    user_id: int
    board: ApplicationBoard
    has_credential: bool = False
    login_status: AtsLoginStatus = AtsLoginStatus.NOT_CONFIGURED
    last_login_at: datetime | None = None
    last_failure_kind: str | None = None
    created_at: datetime
    updated_at: datetime


class ApiUsage(_Base):
    id: int
    user_id: int
    application_id: int | None = None

    provider: LLMProvider
    model: str
    method: str  # "complete" | "structured" | "stream"
    prompt_name: str | None = None

    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int

    succeeded: bool = True
    error_kind: str | None = None

    occurred_at: datetime
    created_at: datetime


class Settings(_Base):
    user_id: int

    llm_provider: LLMProvider = LLMProvider.ANTHROPIC
    llm_model: str = "claude-3.5-sonnet-20250219"
    llm_fallback_provider: LLMProvider | None = None

    auto_apply_enabled: bool = False
    auto_apply_score_threshold: float = 0.85
    auto_apply_daily_cap: int | None = None

    eager_review_generation: bool = True
    daily_llm_cost_cap_usd: float | None = None

    notify_threshold: float = 0.80
    notify_on_errors: bool = True
    notifications_enabled: dict[str, bool] = Field(default_factory=dict)

    portfolio_cors_allowed_origins: list[str] = Field(
        default_factory=lambda: ["https://crypticsoul.dev"]
    )

    sources_enabled: dict[str, bool] = Field(default_factory=dict)
    source_schedules: dict[str, str] = Field(default_factory=dict)
    workday_companies: list[str] = Field(default_factory=list)

    deployment_mode: DeploymentMode = DeploymentMode.SELF_HOSTED

    # Plan 10b (item 4, 2026-05-03): single-user signup gate. Mirrors the
    # `Settings.allow_multiple_users` SQLModel column so the shadow stays
    # round-trippable through `db.seed:_shadow_to_payload`.
    allow_multiple_users: bool = False

    debug: bool = False

    created_at: datetime
    updated_at: datetime


__all__ = [
    "User",
    "Profile",
    "Experience",
    "Bullet",
    "Skill",
    "Education",
    "Project",
    "Certification",
    "Job",
    "JobScrapeRun",
    "Application",
    "Contact",
    "ContactApplicationLink",
    "OutreachMessage",
    "EmailThread",
    "AppEvent",
    "GeneratedDocument",
    "ApplicationScreenerAnswer",
    "ATSCredential",
    "ApiUsage",
    "Settings",
]
