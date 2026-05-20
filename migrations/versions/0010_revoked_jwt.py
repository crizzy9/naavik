"""Revoked JWT denylist table.

Revision ID: 0010_revoked_jwt
Revises: 0009_pickle_to_json_jobs
Create Date: 2026-05-20

Per docs/plans/50-0.2.1-security-batched-closeout.md § D.2. Adds
`revoked_jwt(id, jti, user_id, revoked_at, expires_at)` with a unique
index on `jti` for O(1) auth-path lookups + an `expires_at` index to
keep the daily cleanup cron scan fast.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_revoked_jwt"
down_revision: str | None = "0009_pickle_to_json_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "revoked_jwt",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("jti", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.UniqueConstraint("jti", name="uq_revoked_jwt_jti"),
    )
    op.create_index("ix_revoked_jwt_jti", "revoked_jwt", ["jti"])
    op.create_index("ix_revoked_jwt_user_id", "revoked_jwt", ["user_id"])
    op.create_index("ix_revoked_jwt_expires_at", "revoked_jwt", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_revoked_jwt_expires_at", table_name="revoked_jwt")
    op.drop_index("ix_revoked_jwt_user_id", table_name="revoked_jwt")
    op.drop_index("ix_revoked_jwt_jti", table_name="revoked_jwt")
    op.drop_table("revoked_jwt")
