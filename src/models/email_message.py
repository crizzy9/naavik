"""EmailMessage entity — per-message inbox row (plan 90 / 0.5.0.01).

Privacy-first storage shape (plan § A.3.c lock): metadata + 200-char snippet
only. Full body is NOT persisted; re-classification refetches from IMAP if
needed. Full-body opt-in is filed as `0.5.0.05a` follow-up.

Sibling to `EmailThread`. EmailThread's inline `messages: list` JSONB column
remains for backward-compat (read-only legacy); new code writes EmailMessage
rows authoritatively.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, Index, UniqueConstraint
from sqlmodel import Field, SQLModel

from ._common import utcnow
from .enums import ApplicationStatus, EmailClassification, UnclassifiedReason


class EmailMessage(SQLModel, table=True):
    __tablename__ = "email_message"
    __table_args__ = (
        UniqueConstraint(
            "thread_id",
            "message_id_external",
            name="uq_email_message_external",
        ),
        CheckConstraint(
            "provider IN ('gmail', 'outlook', 'imap')",
            name="ck_email_message_provider_vocab",
        ),
        Index(
            "ix_email_message_thread_received",
            "thread_id",
            "received_at",
        ),
        Index(
            "ix_email_message_user_class_received",
            "user_id",
            "classification",
            "received_at",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", ondelete="CASCADE", index=True)
    thread_id: int = Field(foreign_key="email_thread.id", ondelete="CASCADE", index=True)
    application_id: int | None = Field(
        default=None,
        foreign_key="application.id",
        ondelete="SET NULL",
        index=True,
    )
    account_id: int | None = Field(
        default=None,
        foreign_key="email_account.id",
        ondelete="SET NULL",
        index=True,
    )

    provider: str
    message_id_external: str
    sender_email: str
    sender_name: str | None = None
    subject: str
    snippet: str = Field(max_length=240)
    # Plan 95 § 3.9.1 — the message's IMAP UID, persisted so the on-demand
    # body route can BODY.PEEK the full text without storing it. NULL for
    # pre-95l rows (the chain falls back to the provider deep-link).
    imap_uid: str | None = Field(default=None, max_length=20)
    # Opt-in stored plaintext excerpt (per-account toggle, default OFF):
    # 2,000 chars — the classifier's context lever and the chain's instant
    # reading surface. The at-rest privacy default stays snippet-only.
    body_excerpt: str | None = Field(default=None, max_length=2000)
    received_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )

    classification: EmailClassification | None = None
    auto_classified: bool = Field(default=True)
    classification_model: str | None = None
    # 2026-07 tracking redesign: employer/role the classifier extracted from
    # the email text. Powers company→application matching and the "detected
    # interview processes" panel for out-of-Naavik applications.
    extracted_company: str | None = Field(default=None, max_length=160)
    extracted_role: str | None = Field(default=None, max_length=160)
    # Interview stage hint ("screen" | "interview") for interview_request
    # emails — drives stage-aware status mapping + process-stage derivation.
    extracted_stage: str | None = Field(default=None, max_length=20)
    # Plan 95 § 3.1 — the specific interview round the email names
    # (InterviewRound.kind vocabulary); drives the round upsert.
    extracted_round_kind: str | None = Field(default=None, max_length=30)
    # Plan 95 § 3.3 — who is talking: employer | ats | agency_recruiter |
    # platform | outplacement | other. Agency mail with no end-client parks
    # in a collapsed group instead of becoming a detected process.
    extracted_sender_type: str | None = Field(default=None, max_length=20)
    # The company an agency is hiring FOR, when the email names one verbatim.
    extracted_end_client: str | None = Field(default=None, max_length=160)
    # Stamped when the user dismisses the detected-process group this message
    # belongs to ("not mine / stop suggesting").
    process_dismissed_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    classification_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    unclassified_reason: UnclassifiedReason | None = None
    urgency: str | None = None

    suggested_status: ApplicationStatus | None = None
    suggested_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    suggestion_dismissed_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    suggestion_applied_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )

    # Item 5 (2026-07): application-inference marker — the receipt detector
    # visits every message once; NULL = not yet examined.
    inference_processed_at: datetime | None = Field(
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
