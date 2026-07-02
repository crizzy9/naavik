"""Project.kind — open-source contributions join the career dossier.

Revision ID: 0029_project_kind
Revises: 0028_auto_apply_states
Create Date: 2026-07-02

Open-source contributions share the Project shape (title/text/link/tags)
but are their own dossier section on /profile and their own list in the
tailoring payload. A `kind` discriminator ("project" | "open_source")
beats a new child table: same fields, same soft-delete semantics, and the
portfolio sync keeps working unchanged for kind='project'.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029_project_kind"
down_revision: str | None = "0028_auto_apply_states"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "project",
        sa.Column(
            "kind",
            sa.String(length=20),
            nullable=False,
            server_default="project",
        ),
    )


def downgrade() -> None:
    op.drop_column("project", "kind")
