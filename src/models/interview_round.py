"""InterviewRound — rounds within a pipeline stage (plan 95 § 3.1).

A round never IS a stage — it EVIDENCES one. The six-value
`ApplicationStatus` stays the board/KPI contract; rounds are the queryable
sub-structure ("Camber ran a technical screen AND a system design round")
with links back to the email / calendar event that evidenced them.

`kind` is a string + CHECK vocabulary (the 0040 pattern), NOT a native
enum — the list WILL grow as new interview formats appear, and extending a
CHECK is a two-line migration. Novel formats land as `other` + verbatim
`title`; accumulation under `other` is the signal to extend the vocab.

Clubbed onsite loops (owner decision 2026-07-07): a 3–5-interview block the
company delivers as one invite is ONE round of `kind=onsite_loop` whose
`sessions` JSONB itemizes the segments — one gate, one outcome, one date.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from ._common import utcnow

ROUND_KINDS = (
    "recruiter_screen",
    "technical_screen",
    "take_home",
    "system_design",
    "hiring_manager",
    "builder_interview",
    "team_match",
    "panel",
    "onsite_loop",
    "other",
)
ROUND_STATES = ("planned", "scheduled", "completed", "cancelled")
ROUND_OUTCOMES = ("passed", "failed", "pending")
ROUND_SOURCES = ("email", "calendar", "notes", "manual")

# Kinds that evidence the ONSITE_LOOP ("Interview Stage") pipeline stage
# when completed/scheduled; recruiter_screen evidences RECRUITER_SCREEN.
ONSITE_EVIDENCE_KINDS = frozenset(
    {
        "technical_screen",
        "take_home",
        "system_design",
        "hiring_manager",
        "builder_interview",
        "team_match",
        "panel",
        "onsite_loop",
    }
)


class InterviewRound(SQLModel, table=True):
    __tablename__ = "interview_round"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('recruiter_screen', 'technical_screen', 'take_home', "
            "'system_design', 'hiring_manager', 'builder_interview', "
            "'team_match', 'panel', 'onsite_loop', 'other')",
            name="ck_interview_round_kind_vocab",
        ),
        CheckConstraint(
            "state IN ('planned', 'scheduled', 'completed', 'cancelled')",
            name="ck_interview_round_state_vocab",
        ),
        CheckConstraint(
            "outcome IS NULL OR outcome IN ('passed', 'failed', 'pending')",
            name="ck_interview_round_outcome_vocab",
        ),
        CheckConstraint(
            "source IN ('email', 'calendar', 'notes', 'manual')",
            name="ck_interview_round_source_vocab",
        ),
        Index("ix_interview_round_application_no", "application_id", "round_no"),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", ondelete="CASCADE", index=True)
    application_id: int = Field(foreign_key="application.id", ondelete="CASCADE", index=True)

    round_no: int = Field(default=1)  # display order only
    kind: str = Field(max_length=30)
    title: str | None = Field(default=None, max_length=200)
    state: str = Field(default="planned", max_length=20)
    scheduled_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    # Clubbed-loop sub-sessions: [{title, starts_at?, interviewer?, kind_hint?}]
    sessions: list = Field(default_factory=list, sa_column=Column(JSONB, nullable=False))
    outcome: str | None = Field(default=None, max_length=20)
    source: str = Field(default="manual", max_length=20)

    email_message_id: int | None = Field(
        default=None,
        foreign_key="email_message.id",
        ondelete="SET NULL",
    )
    calendar_event_id: int | None = Field(
        default=None,
        foreign_key="calendar_event.id",
        ondelete="SET NULL",
    )
    notes: str | None = Field(default=None, max_length=2000)

    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
