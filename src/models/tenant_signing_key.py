"""Per-tenant JWT signing key — plan 62 (0.2.7.07).

One row per signing key per tenant. Status lifecycle:

  ACTIVE   — signs all new tokens for the tenant. Exactly one per tenant.
  RETIRING — verifies in-flight tokens during the grace window after rotation.
             Does NOT sign new tokens.
  RETIRED  — archived; rejects verification. Kept forever for forensics
             (incident response — "which key signed this disputed JWT?").

Algorithm is per-row so the env-legacy HS256 row planted by alembic 0014
coexists with operator-issued RS256 rows. The `kid` claim in the JWT
header carries the row's `kid`; verifier resolves the row, runs
algorithm-specific decode against either `public_key_pem` (RS256/EdDSA)
or `private_key_pem` (HS256 shared secret).

Key material — both PEM columns — sits in postgres at-rest. Operator's
host config is the trust boundary (same model as `users.password_hash`).
The vault is sunset (plan 26 / 0.2.0.01); encrypted-at-rest local stores
are forbidden.

Canonical reference: `docs/design/JWT_ROTATION.md` (graduated from plan 62).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Index, Text
from sqlmodel import Field, SQLModel

from ._common import utcnow
from .enums import SigningAlgorithm, TenantSigningKeyStatus


class TenantSigningKey(SQLModel, table=True):
    __tablename__ = "tenant_signing_key"
    __table_args__ = (Index("ix_tenant_signing_key_tenant_status", "tenant_id", "status"),)

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", nullable=False, index=True)
    kid: str = Field(nullable=False, max_length=64, unique=True, index=True)
    algorithm: SigningAlgorithm
    status: TenantSigningKeyStatus = Field(default=TenantSigningKeyStatus.ACTIVE)

    # PEM-encoded. For RS256/EdDSA: public + private. For HS256:
    # `private_key_pem` carries the shared-secret bytes (URL-safe base64);
    # `public_key_pem` is NULL.
    public_key_pem: str | None = Field(
        default=None,
        sa_column=Column(Text(), nullable=True),
    )
    private_key_pem: str | None = Field(
        default=None,
        sa_column=Column(Text(), nullable=True),
    )

    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    activated_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    retired_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
