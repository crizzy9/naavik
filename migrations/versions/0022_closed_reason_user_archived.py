"""Add user_archived to closedreason enum — plan 80 (0.4.0.09).

Revision ID: 0022_closed_reason_user_archived
Revises: 0021_auto_apply_hardening
Create Date: 2026-05-21

Adds a new value `user_archived` to the existing `closedreason` Postgres ENUM
type so the new `application_service.bulk_archive` flow can mark applications
CLOSED with `closed_reason=USER_ARCHIVED` (vs the existing reject / withdraw /
ghost / accepted_other vocabulary).

Additive ENUM add via `ALTER TYPE ... ADD VALUE` inside an autocommit block
(mirrors plan 38 / 0008 + plan 78 / 0021 ENUM-add precedent). Downgrade is a
no-op — pre-PG16 can't drop enum values, and pre-existing rows referencing the
value would be left dangling regardless.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0022_closed_reason_user_archived"
down_revision: str | None = "0021_auto_apply_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # SQLite uses a String-backed enum; new values just work.
        return
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE closedreason ADD VALUE IF NOT EXISTS 'user_archived'")


def downgrade() -> None:
    # Pre-PG16 ENUM types can't drop values. No-op by design (matches plan 27 /
    # 0005 + plan 78 / 0021 ENUM-add downgrades).
    return
