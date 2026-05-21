"""Partial unique index — one ACTIVE signing key per tenant.

Revision ID: 0015_tenant_signing_key_active_uniq
Revises: 0014_tenant_signing_keys
Create Date: 2026-05-20

DB-level invariant making two concurrent ACTIVE rows for the same tenant
impossible regardless of code. Closes hacker MED-1 finding on PR #163:
rotate_tenant_key's select-modify-insert sequence had no `SELECT FOR UPDATE`
or unique constraint; two close-in-time operator clicks could leave two
ACTIVE rows, breaking `_get_active_signing_key`'s `.one_or_none()` assertion.

Partial-index form `WHERE status = 'ACTIVE'` is supported by both Postgres
and SQLite. Existing RETIRING/RETIRED rows do not count toward the unique
constraint, so the 0014 backfill (one env-legacy ACTIVE row per tenant)
satisfies the invariant on apply.

The 0014 migration plants exactly one ACTIVE row per tenant during apply,
so this index lands clean. Conflict surfaces as `IntegrityError` on
concurrent rotation flushes — the rotate endpoint catches and returns 409.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_tenant_signing_key_active_uniq"
down_revision: str | None = "0014_tenant_signing_keys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_INDEX_NAME = "ix_tenant_signing_key_one_active_per_tenant"


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.create_index(
            _INDEX_NAME,
            "tenant_signing_key",
            ["tenant_id"],
            unique=True,
            postgresql_where=sa.text("status = 'ACTIVE'"),
        )
    else:
        op.create_index(
            _INDEX_NAME,
            "tenant_signing_key",
            ["tenant_id"],
            unique=True,
            sqlite_where=sa.text("status = 'ACTIVE'"),
        )


def downgrade() -> None:
    op.drop_index(_INDEX_NAME, table_name="tenant_signing_key")
