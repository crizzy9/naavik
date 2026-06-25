"""Profile.raw_resume_text column — plan 0.7.0.48 Wave 3 fold-in.

Revision ID: 0023_profile_raw_resume_text
Revises: 0022_closed_reason_user_archived
Create Date: 2026-05-25

Holds the most-recent resume PDF's extracted plaintext (pdfplumber output).
Surfaced read-only on `/profile/edit` so operators can see what the heuristic
parser saw. Nullable — pre-existing rows + users who never upload stay NULL.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_profile_raw_resume_text"
down_revision: str | None = "0022_closed_reason_user_archived"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "profile",
        sa.Column("raw_resume_text", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("profile", "raw_resume_text")
