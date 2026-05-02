"""Job entity — pre-application opportunities (scraped or manual).

Per DATA_MODEL.md § C `Job`. `queue_state` flips to `applied` when an
Application transitions to APPLIED. `match_breakdown` is JSONB with
tag → score mapping.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, Index, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlmodel import Field, SQLModel

from ._common import utcnow
from .enums import ApplicationBoard, JobQueueState, JobSource


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
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)

    source: JobSource
    board: ApplicationBoard
    url: str = Field(index=True)
    url_type: str

    company: str
    role: str
    team: str | None = None
    location: str | None = None

    posted_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    found_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )

    description: str
    description_html: str | None = None
    criteria: list[str] = Field(
        default_factory=list,
        sa_column=Column(ARRAY(String), nullable=False, server_default="{}"),
    )
    skills_required: list[str] = Field(
        default_factory=list,
        sa_column=Column(ARRAY(String), nullable=False, server_default="{}"),
    )
    visa_restrictions: str | None = None

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

