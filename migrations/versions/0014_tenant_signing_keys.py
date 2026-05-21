"""Tenant + TenantSigningKey + Settings JWT-rotation columns.

Revision ID: 0014_tenant_signing_keys
Revises: 0013_job_embedding
Create Date: 2026-05-20

Per docs/plans/62-0.2.7.07-jwt-rotation.md § B.1, with the version-bump
deviation applied (plan said 0011, but plans 0011-0013 already shipped for
auto-apply / profile-answer / job-embedding).

Creates `tenant` (single-row self-host root) + `tenant_signing_key`
(per-key audit trail) + 2 new ENUM types (`signingalgorithm`,
`tenantsigningkeystatus`) + 2 Settings columns (`jwt_rotation_days`,
`jwt_rotation_grace_days`).

Backfill (OQ.8 force-migrate path): on first apply, insert one
`Tenant(id=1, name='self-hosted')` if missing, then materialize one
`TenantSigningKey` row carrying the current `SECRET_KEY` env value as an
HS256 shared secret (`kid='env-legacy'`, `algorithm=HS256`, `status=ACTIVE`).
This lets pre-existing Phase 1 self-host installs keep verifying tokens
issued before this migration. Operator rotates to RS256 via the Settings
UI button.

Round-trip test: `tests/test_alembic_0014.py`.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0014_tenant_signing_keys"
down_revision: str | None = "0013_job_embedding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_SIGNING_ALGORITHM_VALUES = ("HS256", "RS256", "EdDSA")
_TENANT_SIGNING_KEY_STATUS_VALUES = ("ACTIVE", "RETIRING", "RETIRED")


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # ── 1. ENUM types (Postgres only; sqlite uses varchar) ───────────────
    if is_postgres:
        op.execute(
            "CREATE TYPE signingalgorithm AS ENUM ("
            + ", ".join(f"'{v}'" for v in _SIGNING_ALGORITHM_VALUES)
            + ")"
        )
        op.execute(
            "CREATE TYPE tenantsigningkeystatus AS ENUM ("
            + ", ".join(f"'{v}'" for v in _TENANT_SIGNING_KEY_STATUS_VALUES)
            + ")"
        )
        algorithm_type = sa.dialects.postgresql.ENUM(
            *_SIGNING_ALGORITHM_VALUES, name="signingalgorithm", create_type=False
        )
        status_type = sa.dialects.postgresql.ENUM(
            *_TENANT_SIGNING_KEY_STATUS_VALUES,
            name="tenantsigningkeystatus",
            create_type=False,
        )
    else:
        algorithm_type = sa.String(length=16)
        status_type = sa.String(length=16)

    # ── 2. tenant ────────────────────────────────────────────────────────
    op.create_table(
        "tenant",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name", name="uq_tenant_name"),
    )
    op.create_index("ix_tenant_name", "tenant", ["name"])

    # ── 3. tenant_signing_key ────────────────────────────────────────────
    op.create_table(
        "tenant_signing_key",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("kid", sa.String(length=64), nullable=False),
        sa.Column("algorithm", algorithm_type, nullable=False),
        sa.Column("status", status_type, nullable=False),
        sa.Column("public_key_pem", sa.Text(), nullable=True),
        sa.Column("private_key_pem", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.UniqueConstraint("kid", name="uq_tenant_signing_key_kid"),
    )
    op.create_index("ix_tenant_signing_key_kid", "tenant_signing_key", ["kid"])
    op.create_index("ix_tenant_signing_key_tenant_id", "tenant_signing_key", ["tenant_id"])
    op.create_index(
        "ix_tenant_signing_key_tenant_status",
        "tenant_signing_key",
        ["tenant_id", "status"],
    )

    # ── 4. settings columns ──────────────────────────────────────────────
    op.add_column(
        "settings",
        sa.Column(
            "jwt_rotation_days",
            sa.Integer(),
            nullable=False,
            server_default="90",
        ),
    )
    op.add_column(
        "settings",
        sa.Column(
            "jwt_rotation_grace_days",
            sa.Integer(),
            nullable=False,
            server_default="7",
        ),
    )

    # ── 5. Backfill — env-legacy HS256 row (OQ.8) ────────────────────────
    # Idempotent: skip insert when a tenant row already exists. Reading
    # SECRET_KEY at migration time means the value gets persisted; future
    # rotations replace it. If the env is unset (rare — config.py validators
    # would refuse to boot outside NAAVIK_DEBUG), fall back to a freshly
    # generated 32-byte URL-safe secret so the table is never empty.
    now = datetime.now(UTC)
    op.execute(
        sa.text(
            "INSERT INTO tenant (id, name, created_at) "
            "SELECT 1, 'self-hosted', :now "
            "WHERE NOT EXISTS (SELECT 1 FROM tenant WHERE id = 1)"
        ).bindparams(now=now)
    )

    legacy_secret = os.environ.get("SECRET_KEY") or secrets.token_urlsafe(32)
    op.execute(
        sa.text(
            "INSERT INTO tenant_signing_key "
            "(tenant_id, kid, algorithm, status, public_key_pem, "
            "private_key_pem, created_at, activated_at) "
            "SELECT 1, 'env-legacy', 'HS256', 'ACTIVE', NULL, "
            ":secret, :now, :now "
            "WHERE NOT EXISTS (SELECT 1 FROM tenant_signing_key WHERE kid = 'env-legacy')"
        ).bindparams(secret=legacy_secret, now=now)
    )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    op.drop_column("settings", "jwt_rotation_grace_days")
    op.drop_column("settings", "jwt_rotation_days")

    op.drop_index("ix_tenant_signing_key_tenant_status", table_name="tenant_signing_key")
    op.drop_index("ix_tenant_signing_key_tenant_id", table_name="tenant_signing_key")
    op.drop_index("ix_tenant_signing_key_kid", table_name="tenant_signing_key")
    op.drop_table("tenant_signing_key")

    op.drop_index("ix_tenant_name", table_name="tenant")
    op.drop_table("tenant")

    if is_postgres:
        op.execute("DROP TYPE IF EXISTS tenantsigningkeystatus")
        op.execute("DROP TYPE IF EXISTS signingalgorithm")
