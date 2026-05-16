"""settings.allow_multiple_users — single-user signup gate.

Revision ID: 0002_settings_multi_users
Revises: 0001_initial
Create Date: 2026-05-03

Plan 10b (item 4): adds a boolean toggle on the Settings singleton that
gates `POST /api/v1/auth/signup`. Default `false` keeps a self-hosted
instance from accidentally turning into a multi-tenant SaaS once the
first User row exists. Multi-user proper is Phase 2+.

NOTE: revision id is intentionally short — Alembic stores `version_num`
in `varchar(32)` by default. The descriptive `allow_multiple_users`
lives in the docstring + the column name, not the revision slug.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_settings_multi_users"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "settings",
        sa.Column(
            "allow_multiple_users",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("settings", "allow_multiple_users")
