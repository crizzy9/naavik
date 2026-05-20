"""ProfileAnswer reuse cache — plan 61 (0.2.7.14).

Revision ID: 0012_profile_answer
Revises: 0011_settings_auto_apply_immediate
Create Date: 2026-05-20

Per `docs/plans/61-0.2.7.14-0.2.7.16-profile-answer-job-embedding.md` § B.1.
Additive single-table migration; reversible. Decision D10 keeps this
separate from 0013_job_embedding so a self-hoster who hits pgvector
trouble can `alembic downgrade 0012` without losing the reuse cache.

Round-trip test: `tests/test_alembic_0012.py`.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_profile_answer"
down_revision: str | None = "0011_settings_auto_apply_immediate"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "profile_answer",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("user.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("question_fingerprint", sa.String(length=256), nullable=False, index=True),
        sa.Column("question_text_sample", sa.String(length=1024), nullable=False),
        sa.Column("answer", sa.String(length=8192), nullable=False),
        sa.Column(
            "source_screener_answer_id",
            sa.Integer(),
            sa.ForeignKey("application_screener_answer.id"),
            nullable=False,
        ),
        sa.Column("times_offered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("times_accepted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "user_id",
            "question_fingerprint",
            name="uq_profile_answer_user_fingerprint",
        ),
    )
    op.create_index(
        "ix_profile_answer_user_last_used",
        "profile_answer",
        ["user_id", "last_used_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_profile_answer_user_last_used", "profile_answer")
    op.drop_table("profile_answer")
