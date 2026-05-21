"""Application.generation_trace + 5 Settings.generation fields — plan 66 (0.3.1).

Revision ID: 0018_generation_trace_and_settings
Revises: 0017_scorer_settings
Create Date: 2026-05-21

Per docs/plans/66-0.3.1-free-tier-generation.md § T14. JSONB on Postgres,
JSON on sqlite (tests). Opaque-blob pattern matching `submission_artifacts`
precedent — schema enforced in the Pydantic GenerationTrace model, not at
the DB layer.

Settings columns are NOT NULL with server_default; existing rows get the
default on upgrade.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0018_generation_trace_and_settings"
down_revision: str | None = "0017_scorer_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    json_type = JSONB() if is_postgres else sa.JSON()

    op.add_column(
        "application",
        sa.Column("generation_trace", json_type, nullable=True),
    )

    op.add_column(
        "settings",
        sa.Column(
            "ai_writing_voice_samples",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
    )
    op.add_column(
        "settings",
        sa.Column(
            "cover_letter_format",
            sa.String(length=20),
            nullable=False,
            server_default="auto",
        ),
    )
    op.add_column(
        "settings",
        sa.Column(
            "tier_2_evasion_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "settings",
        sa.Column(
            "resume_template_preference",
            sa.String(length=20),
            nullable=False,
            server_default="auto",
        ),
    )
    op.add_column(
        "settings",
        sa.Column(
            "parse_fidelity_threshold",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.75"),
        ),
    )


def downgrade() -> None:
    op.drop_column("settings", "parse_fidelity_threshold")
    op.drop_column("settings", "resume_template_preference")
    op.drop_column("settings", "tier_2_evasion_enabled")
    op.drop_column("settings", "cover_letter_format")
    op.drop_column("settings", "ai_writing_voice_samples")
    op.drop_column("application", "generation_trace")
