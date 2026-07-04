"""Project/Certification selection_override — three-state include control.

Revision ID: 0036_section_selection_override
Revises: 0035_apply_retry
Create Date: 2026-07-03

Resume tailoring could pin or ban individual bullets
(`bullet.selection_override`) but had no equivalent for the single-line
Projects / Certifications / Open-Source rows — every row always rendered.
These columns reuse the existing `bulletselectionoverride` Postgres enum:
`ALWAYS_INCLUDE` / `NEVER_INCLUDE` / NULL (tailoring decides by remaining
page space).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0036_section_selection_override"
down_revision: str | None = "0035_apply_retry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Reuse the enum type 0001 created for bullet.selection_override.
_OVERRIDE = postgresql.ENUM(
    "ALWAYS_INCLUDE", "NEVER_INCLUDE", name="bulletselectionoverride", create_type=False
)


def upgrade() -> None:
    op.add_column("project", sa.Column("selection_override", _OVERRIDE, nullable=True))
    op.add_column("certification", sa.Column("selection_override", _OVERRIDE, nullable=True))


def downgrade() -> None:
    op.drop_column("certification", "selection_override")
    op.drop_column("project", "selection_override")
