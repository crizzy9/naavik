"""JWT signing-key rotation service — plan 62 (0.2.7.07).

Three async functions own the lifecycle:

  rotate_tenant_key(session, tenant_id, *, algorithm=RS256, actor)
      Generate a new keypair, mark the current ACTIVE row → RETIRING (with
      `retired_at = now()`), insert the new row as ACTIVE. Atomic — both
      operations live in the caller's transaction. Caller commits.

  expire_retiring_keys(session, *, settings_by_tenant)
      Sweep RETIRING rows; flip to RETIRED when `retired_at + grace_window`
      is in the past. Idempotent — safe to call every scheduler tick.
      Reads per-tenant `jwt_rotation_grace_days` from a {tenant_id: int}
      grace-window map (cron pre-loads it from Settings rows).

  ensure_active_key(session, *, tenant_id, algorithm=RS256)
      Safety net invoked by the signer when a tenant somehow has zero
      ACTIVE keys (rare — only the rotation transaction rolling back
      mid-execution). Generates one RS256 keypair on demand.

Per-tenant blast-radius isolation: each tenant's rotations touch only
their own rows. Self-host single-tenant degrades to the same code path
with `tenant_id=1`.

The vault is sunset (plan 26 / 0.2.0.01); private keys sit in postgres
at-rest. Operator's host config is the trust boundary — same model as
`users.password_hash` already assumes.
"""

from __future__ import annotations

import base64
import logging
import secrets
from datetime import UTC, datetime, timedelta

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import SigningAlgorithm, TenantSigningKey, TenantSigningKeyStatus

log = logging.getLogger(__name__)

_RSA_KEY_SIZE_BITS = 2048
_KID_BYTES = 8  # 8 bytes → 11 url-safe chars


def _generate_kid() -> str:
    """8-byte url-safe random; fits the JWT header `kid` claim comfortably."""
    return secrets.token_urlsafe(_KID_BYTES)


def _generate_keypair(
    algorithm: SigningAlgorithm,
) -> tuple[str | None, str]:
    """Return `(public_key_pem, private_key_pem_or_secret)` for `algorithm`.

    HS256 ships shared-secret bytes in the private slot (public is NULL).
    RS256 ships PEM-encoded RSA-2048 keypair. EdDSA reserved for future
    rotation paths; not exercised by the v1 UI button.
    """
    if algorithm == SigningAlgorithm.HS256:
        return None, secrets.token_urlsafe(48)
    if algorithm == SigningAlgorithm.RS256:
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=_RSA_KEY_SIZE_BITS,
        )
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")
        public_pem = (
            private_key.public_key()
            .public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode("utf-8")
        )
        return public_pem, private_pem
    raise ValueError(f"unsupported signing algorithm: {algorithm}")


async def rotate_tenant_key(
    session: AsyncSession,
    *,
    tenant_id: int,
    algorithm: SigningAlgorithm = SigningAlgorithm.RS256,
    actor: str = "system",
) -> TenantSigningKey:
    """Promote the current ACTIVE key to RETIRING + insert a fresh ACTIVE row.

    Caller commits. Order matters: we flip the old row's status BEFORE
    inserting the new row so the per-tenant invariant `<=1 ACTIVE` survives
    even if the new insert's flush fires constraint checks.
    """
    now = datetime.now(UTC)
    stmt = select(TenantSigningKey).where(
        TenantSigningKey.tenant_id == tenant_id,
        TenantSigningKey.status == TenantSigningKeyStatus.ACTIVE,
    )
    current = (await session.exec(stmt)).one_or_none()
    if current is not None:
        current.status = TenantSigningKeyStatus.RETIRING
        current.retired_at = now
        session.add(current)
        await session.flush()

    public_pem, private_pem = _generate_keypair(algorithm)
    fresh = TenantSigningKey(
        tenant_id=tenant_id,
        kid=_generate_kid(),
        algorithm=algorithm,
        status=TenantSigningKeyStatus.ACTIVE,
        public_key_pem=public_pem,
        private_key_pem=private_pem,
        created_at=now,
        activated_at=now,
    )
    session.add(fresh)
    await session.flush()
    log.info(
        "jwt_rotation rotate tenant=%d algorithm=%s actor=%s new_kid=%s",
        tenant_id,
        algorithm.value,
        actor,
        fresh.kid,
    )
    return fresh


async def expire_retiring_keys(
    session: AsyncSession,
    *,
    grace_days_by_tenant: dict[int, int] | None = None,
    default_grace_days: int = 7,
) -> int:
    """Flip RETIRING → RETIRED when the per-tenant grace window has elapsed.

    `grace_days_by_tenant` lets the cron use Settings-resolved windows per
    tenant; absent entries fall back to `default_grace_days`. Returns the
    count of rows flipped. Idempotent.
    """
    now = datetime.now(UTC)
    by_tenant = grace_days_by_tenant or {}
    stmt = select(TenantSigningKey).where(
        TenantSigningKey.status == TenantSigningKeyStatus.RETIRING,
        TenantSigningKey.retired_at.is_not(None),  # type: ignore[union-attr]
    )
    rows = (await session.exec(stmt)).all()
    flipped = 0
    for row in rows:
        grace = by_tenant.get(row.tenant_id, default_grace_days)
        retired_at = row.retired_at
        if retired_at is None:
            continue
        if retired_at.tzinfo is None:
            retired_at = retired_at.replace(tzinfo=UTC)
        cutoff = retired_at + timedelta(days=grace)
        if cutoff <= now:
            row.status = TenantSigningKeyStatus.RETIRED
            # Wipe the private material on terminal transition — RETIRED
            # rows only need the public-key + audit columns. Public PEM
            # stays around so the row remains forensically useful.
            row.private_key_pem = None
            session.add(row)
            flipped += 1
    if flipped:
        await session.flush()
        log.info("jwt_rotation expire_retiring_keys flipped=%d", flipped)
    return flipped


async def ensure_active_key(
    session: AsyncSession,
    *,
    tenant_id: int,
    algorithm: SigningAlgorithm = SigningAlgorithm.RS256,
) -> TenantSigningKey:
    """Return the tenant's ACTIVE key, materializing one if none exists.

    Safety net for the lockout case in plan 62 § F (rotation transaction
    rolls back mid-execution). Returns the existing ACTIVE row when one
    exists — never duplicates.
    """
    stmt = select(TenantSigningKey).where(
        TenantSigningKey.tenant_id == tenant_id,
        TenantSigningKey.status == TenantSigningKeyStatus.ACTIVE,
    )
    existing = (await session.exec(stmt)).one_or_none()
    if existing is not None:
        return existing
    now = datetime.now(UTC)
    public_pem, private_pem = _generate_keypair(algorithm)
    fresh = TenantSigningKey(
        tenant_id=tenant_id,
        kid=_generate_kid(),
        algorithm=algorithm,
        status=TenantSigningKeyStatus.ACTIVE,
        public_key_pem=public_pem,
        private_key_pem=private_pem,
        created_at=now,
        activated_at=now,
    )
    session.add(fresh)
    await session.flush()
    log.info(
        "jwt_rotation ensure_active_key bootstrapped tenant=%d kid=%s",
        tenant_id,
        fresh.kid,
    )
    return fresh


def hs256_secret_bytes(key: TenantSigningKey) -> bytes:
    """Decode a TenantSigningKey's HS256 shared secret to raw bytes.

    The shared secret is stored as `secrets.token_urlsafe(48)` output (a
    url-safe-base64 string without padding). PyJWT accepts either bytes
    or strings for HS256, so the call site can pass the string directly;
    this helper exists for tests + future symmetric-rotation paths.
    """
    if key.algorithm != SigningAlgorithm.HS256 or key.private_key_pem is None:
        raise ValueError("hs256_secret_bytes called on non-HS256 key")
    padded = key.private_key_pem + "=" * (-len(key.private_key_pem) % 4)
    return base64.urlsafe_b64decode(padded)


__all__ = [
    "ensure_active_key",
    "expire_retiring_keys",
    "hs256_secret_bytes",
    "rotate_tenant_key",
]
