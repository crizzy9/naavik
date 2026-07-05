"""Per-user reuse cache for screener-question answers.

Plan 61 / `0.2.7.14` (2026-05-20). Keyed by deterministic
`(user_id, question_fingerprint)`; fingerprint algorithm is exact-normalized
v1 (lowercase + strip-punct + remove-company + Porter-stem + SHA-1 prefix)
per decision D6. Semantic-fingerprint upgrade deferred to 0.8.0.

Privacy: per-user only. `search_similar` never crosses tenants — see
`tests/test_no_cross_user_embedding_reads.py` for the regression lint.

Phase 2+ entity (graduates `docs/design/DATA_MODEL.md` § J reuse-cache stub).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Index, UniqueConstraint
from sqlmodel import Field, SQLModel

from ._common import utcnow


class ProfileAnswer(SQLModel, table=True):
    __tablename__ = "profile_answer"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "question_fingerprint",
            name="uq_profile_answer_user_fingerprint",
        ),
        Index(
            "ix_profile_answer_user_last_used",
            "user_id",
            "last_used_at",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    # No single-column index: ix_profile_answer_user_last_used leads with user_id.
    user_id: int = Field(foreign_key="user.id", ondelete="CASCADE")

    question_fingerprint: str = Field(index=True, max_length=256)
    question_text_sample: str = Field(max_length=1024)
    answer: str = Field(max_length=8192)

    source_screener_answer_id: int = Field(
        foreign_key="application_screener_answer.id",
        ondelete="CASCADE",
        index=True,
    )

    times_offered: int = Field(default=0)
    times_accepted: int = Field(default=0)
    last_used_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
