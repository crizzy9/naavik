"""Profile entity + child entities (Experience, Bullet, Skill, Education,
Project, Certification).

Per DATA_MODEL.md § C. Bullets are single long-form text — AI trims at apply
time. The 9-tag vocab + per-bullet `selection_override` drive resume tailoring.
EEO/visa fields are flat columns on Profile; auto-injected into every
application bundle.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlmodel import Field, SQLModel

from ._common import utcnow
from .enums import (
    BulletSelectionOverride,
    DisabilityStatus,
    Gender,
    Race,
    RelocateOpenness,
    VeteranStatus,
    VisaSponsorship,
    WorkAuthorization,
)


class Profile(SQLModel, table=True):
    __tablename__ = "profile"
    __table_args__ = (
        CheckConstraint(
            "salary_expectation_usd IS NULL OR salary_expectation_usd >= 0",
            name="ck_profile_salary_nonneg",
        ),
        CheckConstraint(
            "notice_period_days IS NULL OR notice_period_days >= 0",
            name="ck_profile_notice_nonneg",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", ondelete="CASCADE", unique=True, index=True)

    # Identity
    full_name: str
    headline: str
    current_company: str | None = None
    location: str | None = None
    email: str = Field(index=True, max_length=320)
    phone: str | None = None
    portfolio_url: str | None = None
    github_handle: str | None = None
    linkedin_handle: str | None = None
    open_to_opportunities: bool = Field(default=True)

    # Summary
    summary_full: str | None = None
    summary_short: str | None = None

    # US application questions (Phase 1 — see DATA_MODEL.md § A note)
    work_authorization: WorkAuthorization | None = None
    visa_sponsorship_needed: VisaSponsorship | None = None
    willing_to_relocate: RelocateOpenness | None = None
    notice_period_days: int | None = None
    salary_expectation_usd: int | None = None
    earliest_start: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    veteran_status: VeteranStatus | None = None
    disability_status: DisabilityStatus | None = None
    race_ethnicity: Race | None = None
    gender_identity: Gender | None = None

    cover_letter_base: dict | None = Field(default=None, sa_column=Column(JSONB, nullable=True))

    # Plan 73 (0.3.2.03): per-role-family 30-day score trends.
    # Written by APScheduler cron `score.aggregate_daily`; consumed by Profile
    # hero sparkline strip. Shape documented in docs/design/DATA_MODEL.md.
    score_history: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
    )

    # Raw plaintext from the most-recent resume upload (pdfplumber extract).
    # Drives the "Raw resume text (parsed source)" panel on /profile/edit so
    # operators can see what the heuristic parser saw.
    raw_resume_text: str | None = Field(default=None, sa_column=Column(Text, nullable=True))

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


class Experience(SQLModel, table=True):
    __tablename__ = "experience"
    __table_args__ = (
        CheckConstraint(
            "end_date IS NULL OR start_date < end_date",
            name="ck_experience_dates",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    profile_id: int = Field(foreign_key="profile.id", ondelete="CASCADE", index=True)

    company: str
    title: str
    team: str | None = None
    location: str | None = None
    start_date: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    end_date: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    order_index: int = Field(default=0)
    summary_short: str | None = None

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


class Bullet(SQLModel, table=True):
    __tablename__ = "bullet"
    __table_args__ = (
        CheckConstraint("char_length(text) > 0", name="ck_bullet_text_nonempty"),
        Index("ix_bullet_tags_gin", "tags", postgresql_using="gin"),
    )

    id: int | None = Field(default=None, primary_key=True)
    experience_id: int = Field(foreign_key="experience.id", ondelete="CASCADE", index=True)
    order_index: int = Field(default=0)

    text: str
    tags: list[str] = Field(
        default_factory=list,
        sa_column=Column(ARRAY(String), nullable=False, server_default="{}"),
    )
    selection_override: BulletSelectionOverride | None = None

    edited_at: datetime | None = Field(
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
    deleted_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )


class Skill(SQLModel, table=True):
    __tablename__ = "skill"
    __table_args__ = (
        CheckConstraint("char_length(category) > 0", name="ck_skill_category_nonempty"),
    )

    id: int | None = Field(default=None, primary_key=True)
    profile_id: int = Field(foreign_key="profile.id", ondelete="CASCADE", index=True)

    category: str
    items: list[str] = Field(
        default_factory=list,
        sa_column=Column(ARRAY(String), nullable=False, server_default="{}"),
    )
    order_index: int = Field(default=0)

    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class Education(SQLModel, table=True):
    __tablename__ = "education"

    id: int | None = Field(default=None, primary_key=True)
    profile_id: int = Field(foreign_key="profile.id", ondelete="CASCADE", index=True)

    institution: str
    school: str | None = None
    location: str | None = None
    degree: str
    start_date: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    end_date: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    gpa: str | None = None
    courses: list[str] = Field(
        default_factory=list,
        sa_column=Column(ARRAY(String), nullable=False, server_default="{}"),
    )
    order_index: int = Field(default=0)

    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class Project(SQLModel, table=True):
    __tablename__ = "project"
    __table_args__ = (Index("ix_project_tags_gin", "tags", postgresql_using="gin"),)

    id: int | None = Field(default=None, primary_key=True)
    profile_id: int = Field(foreign_key="profile.id", ondelete="CASCADE", index=True)

    title: str
    date: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    text: str
    tags: list[str] = Field(
        default_factory=list,
        sa_column=Column(ARRAY(String), nullable=False, server_default="{}"),
    )
    portfolio_slug: str | None = None
    link: str | None = None
    order_index: int = Field(default=0)

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


class Certification(SQLModel, table=True):
    __tablename__ = "certification"

    id: int | None = Field(default=None, primary_key=True)
    profile_id: int = Field(foreign_key="profile.id", ondelete="CASCADE", index=True)

    title: str
    issuer: str
    date: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    description: str | None = None
    order_index: int = Field(default=0)

    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
