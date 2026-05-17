"""user.must_change_password — PC.6 first-login forced rotation.

Revision ID: 0003_user_must_change_pw
Revises: 0002_settings_multi_users
Create Date: 2026-05-17

Plan 18 (PC.6): boolean flag on User. Set True at seed time when the dev
password is server-generated; cleared by POST /api/v1/auth/change-password
on the first complexity-passing replacement.

Revision id intentionally short — Alembic stores version_num in varchar(32)
by default (see plan 10b's 0002 for the same constraint).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_user_must_change_pw"
down_revision: str | None = "0002_settings_multi_users"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("user", "must_change_password")
