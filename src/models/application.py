"""Application + ApplicationScreenerAnswer + GeneratedDocument + ATSCredential.

Per DATA_MODEL.md § C. The Application CHECK constraint is the corrected
2026-05-01 form covering DRAFT, post-submission, and discarded-DRAFT cases.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlmodel import Field, SQLModel

from ._common import utcnow
from .enums import (
    ApplicationBoard,
    ApplicationStatus,
    AtsLoginStatus,
    ClosedReason,
    DocsState,
    GeneratedDocumentKind,
    RecruiterState,
    ReferralState,
    ScreenerAnswerSource,
    ScreenerQuestionType,
)

# Relationships removed in Wave 3: services use FK joins via select(...). The
# SQLModel relationship-string forward-ref pattern interacted poorly with the
# circular Job ↔ Application ↔ Contact graph in 0.0.22; Wave 6 may revisit
# once SQLModel relationship handling stabilizes (or we move to declarative
# sqlalchemy 2.0 Mapped annotations).


class Application(SQLModel, table=True):
    __tablename__ = "application"
    __table_args__ = (
        CheckConstraint(
            "(status = 'CLOSED' AND closed_reason IS NOT NULL) OR status != 'CLOSED'",
            name="ck_application_closed_reason_required",
        ),
        # Corrected 2026-05-01: covers DRAFT pre-submission, post-submission with
        # applied_at set, AND discarded DRAFTs that flip to CLOSED via discard.
        CheckConstraint(
            "applied_at IS NOT NULL OR status = 'DRAFT' OR deleted_at IS NOT NULL",
            name="ck_application_applied_at_required",
        ),
        Index("ix_application_user_status", "user_id", "status"),
        Index("ix_application_applied_at_desc", "applied_at"),
        Index(
            "ix_application_user_status_recruiter",
            "user_id",
            "status",
            "recruiter_state",
        ),
        Index(
            "ix_application_user_job_alive_unique",
            "user_id",
            "job_id",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    job_id: int | None = Field(default=None, foreign_key="job.id", index=True)

    # Denormalized identifying metadata (resilient to Job mutation)
    company: str
    role: str
    team: str | None = None
    location: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    equity_pct: float | None = None

    # Submission
    applied_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    board: ApplicationBoard | None = None
    external_url: str | None = None

    # Multi-axis state
    status: ApplicationStatus = Field(default=ApplicationStatus.DRAFT)
    closed_reason: ClosedReason | None = None
    docs_state: DocsState = Field(default=DocsState.NONE)
    referral_state: ReferralState = Field(default=ReferralState.NONE)
    recruiter_state: RecruiterState = Field(default=RecruiterState.NONE)

    submission_artifacts: dict | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
    )

    # Plan 66 (0.3.1) — audit trail for bundle generation (resume + cover
    # letter + screeners). Opaque-blob; canonical shape lives in
    # `services/bundle_generator.GenerationTrace`. OVERWRITES on regenerate.
    generation_trace: dict | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
    )

    notes: str | None = None

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


class GeneratedDocument(SQLModel, table=True):
    __tablename__ = "generated_document"
    __table_args__ = (
        Index(
            "ix_generated_document_app_kind_compiled",
            "application_id",
            "kind",
            "compiled_at",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="application.id", index=True)

    kind: GeneratedDocumentKind
    path: str
    byte_size: int
    page_count: int | None = None
    compiled_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    model: str | None = None
    cost_usd: float | None = None
    token_count: int | None = None
    error: str | None = None

    bullet_selection: dict | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
    )

    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class ApplicationScreenerAnswer(SQLModel, table=True):
    __tablename__ = "application_screener_answer"

    id: int | None = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="application.id", index=True)

    question_text: str
    question_fingerprint: str = Field(index=True)
    question_type: ScreenerQuestionType
    choices: list[str] | None = Field(
        default=None,
        sa_column=Column(ARRAY(String), nullable=True),
    )
    required: bool = Field(default=True)
    order_index: int = Field(default=0)

    answer: str | None = None
    source: ScreenerAnswerSource = Field(default=ScreenerAnswerSource.DRAFTED)
    drafted_by_model: str | None = None
    reviewed_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )

    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class ATSCredential(SQLModel, table=True):
    __tablename__ = "ats_credential"
    __table_args__ = (UniqueConstraint("user_id", "board", name="uq_ats_credential_user_board"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    board: ApplicationBoard

    has_credential: bool = Field(default=False)
    login_status: AtsLoginStatus = Field(default=AtsLoginStatus.NOT_CONFIGURED)
    last_login_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    last_failure_kind: str | None = None

    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
