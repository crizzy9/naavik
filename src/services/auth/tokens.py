"""JWT issue/verify (sync env-legacy + async kid-aware) and the revocation
denylist.

Split out of the auth god-module in plan 91 Phase 4.1; behaviour unchanged.

- JWT signing — TWO entry points:
    * Sync `issue_jwt` / `verify_jwt` — legacy HS256 against `SECRET_KEY`.
      Carries `kid="env-legacy"`. Used by pure-unit tests + the on-disk
      env-legacy migration row that alembic 0014 plants. Backwards
      compatible: tokens issued before alembic 0014 verify here.
    * Async `issue_jwt_async` / `verify_jwt_async` — DB-resolved per-tenant
      key. RS256 once the operator rotates via Settings UI. Used by all
      live API + UI routes via FastAPI deps (which already inject an
      AsyncSession).

Canonical reference for rotation: `docs/design/JWT_ROTATION.md` (graduated
from plan 62).
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

import jwt
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from config import settings as app_settings
from models import (
    RevokedJwt,
    SigningAlgorithm,
    TenantSigningKey,
    TenantSigningKeyStatus,
)

# ── Constants ───────────────────────────────────────────────────────────

SESSION_COOKIE = "naavik_session"
JWT_ALGORITHM = "HS256"
JWT_TTL_DEFAULT = timedelta(hours=24)
JWT_TTL_KEEP_SIGNED_IN = timedelta(days=30)

# Plan 62 (0.2.7.07): self-host single-tenant maps to `tenant_id=1`. Cloud
# multi-tenancy (`0.8.0.NN`) replaces this with per-request resolution.
DEFAULT_TENANT_ID = 1
ENV_LEGACY_KID = "env-legacy"


# ── JWT ──────────────────────────────────────────────────────────────────


def issue_jwt(user_id: int, *, keep_signed_in: bool = False) -> str:
    """Issue a fresh HS256 JWT signed with `SECRET_KEY` + `kid=env-legacy`.

    Sync legacy path — kept for pure-unit tests + pre-rotation
    self-host single-tenant deployments. Production callers should use
    `issue_jwt_async` (DB-resolved per-tenant key).
    """
    ttl = JWT_TTL_KEEP_SIGNED_IN if keep_signed_in else JWT_TTL_DEFAULT
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "tid": str(DEFAULT_TENANT_ID),
        "jti": secrets.token_urlsafe(16),
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
    }
    return jwt.encode(
        payload,
        app_settings.secret_key,
        algorithm=JWT_ALGORITHM,
        headers={"kid": ENV_LEGACY_KID},
    )


def verify_jwt(token: str) -> tuple[int, str, datetime] | None:
    """Return `(user_id, jti, expires_at)` on valid JWT; None on expired/invalid.

    Sync legacy path — verifies HS256 against `SECRET_KEY`. Accepts both
    pre-rotation tokens (no `kid` header) and `kid=env-legacy` tokens.
    Rejects any other `kid` value (those must verify via the async path
    against their DB-stored key).

    Plan 50 (0.2.1.04): expanded from `int | None` to a tuple so callers
    can drive the `RevokedJwt` denylist check + persist `expires_at`
    when revoking the current token at password-change time.

    Plan 62 (0.2.7.07): added the `kid` filter so a tampered header
    pointing at a rotated DB key doesn't sneak past the legacy verifier.
    """
    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError:
        return None
    kid = header.get("kid")
    if kid not in (None, ENV_LEGACY_KID):
        return None
    try:
        decoded = jwt.decode(
            token,
            app_settings.secret_key,
            algorithms=[JWT_ALGORITHM],
        )
        sub = decoded.get("sub")
        jti = decoded.get("jti")
        exp = decoded.get("exp")
        if sub is None or not jti or exp is None:
            return None
        return int(sub), str(jti), datetime.fromtimestamp(int(exp), tz=UTC)
    except (jwt.InvalidTokenError, ValueError):
        return None


# ── Async kid-aware signing (plan 62 / 0.2.7.07) ─────────────────────────


async def _get_active_signing_key(
    session: AsyncSession, *, tenant_id: int
) -> TenantSigningKey | None:
    stmt = select(TenantSigningKey).where(
        TenantSigningKey.tenant_id == tenant_id,
        TenantSigningKey.status == TenantSigningKeyStatus.ACTIVE,
    )
    return (await session.exec(stmt)).one_or_none()


async def _get_signing_key_by_kid(session: AsyncSession, *, kid: str) -> TenantSigningKey | None:
    stmt = select(TenantSigningKey).where(TenantSigningKey.kid == kid)
    return (await session.exec(stmt)).one_or_none()


def _signing_material(key: TenantSigningKey) -> tuple[str, str]:
    """Return `(material, algorithm_str)` for signing. HS256 secret lives
    in `private_key_pem`; RS256 private key likewise."""
    if key.private_key_pem is None:
        raise RuntimeError(
            f"signing key kid={key.kid!r} has no private material; row may have been retired"
        )
    return key.private_key_pem, key.algorithm.value


def _verification_material(key: TenantSigningKey) -> str:
    """Return the bytes used by pyjwt.decode. HS256 uses the shared secret;
    RS256 uses the public PEM."""
    if key.algorithm == SigningAlgorithm.HS256:
        if key.private_key_pem is None:
            raise RuntimeError(f"HS256 key kid={key.kid!r} missing secret")
        return key.private_key_pem
    if key.public_key_pem is None:
        raise RuntimeError(f"asymmetric key kid={key.kid!r} missing public material")
    return key.public_key_pem


async def issue_jwt_async(
    session: AsyncSession,
    *,
    user_id: int,
    tenant_id: int = DEFAULT_TENANT_ID,
    keep_signed_in: bool = False,
) -> str:
    """Issue a JWT signed with the tenant's ACTIVE signing key.

    Falls back to `issue_jwt` (sync, env-legacy HS256) when:
      - no ACTIVE key exists for the tenant (fresh-install / test-harness
        before alembic 0014 has run), OR
      - the ACTIVE key's `kid` is `env-legacy` (plan 0.7.0.48 Wave 2 fix:
        symmetry with `verify_jwt_async` which delegates `env-legacy` kid
        to sync `verify_jwt`). Without this branch, the issuer signed with
        the DB row's material — which migration 0014 plants as
        `os.environ.get("SECRET_KEY") or secrets.token_urlsafe(32)`. When
        `SECRET_KEY` is unset (dev default), the migration plants a random
        URL-safe-32 key, but the sync verifier always reads
        `app_settings.secret_key` (`"change-me-in-production"` by default
        in dev) → `InvalidSignatureError` on every authed request →
        "Session expired" 307 → login loop. With this fix the env-legacy
        DB row is informational only; the env material is the single
        source of truth for both issue + verify on the env-legacy path.
    """
    key = await _get_active_signing_key(session, tenant_id=tenant_id)
    if key is None or key.kid == ENV_LEGACY_KID:
        return issue_jwt(user_id, keep_signed_in=keep_signed_in)
    ttl = JWT_TTL_KEEP_SIGNED_IN if keep_signed_in else JWT_TTL_DEFAULT
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "tid": str(tenant_id),
        "jti": secrets.token_urlsafe(16),
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
    }
    material, algorithm = _signing_material(key)
    return jwt.encode(
        payload,
        material,
        algorithm=algorithm,
        headers={"kid": key.kid},
    )


async def verify_jwt_async(
    session: AsyncSession,
    token: str,
    *,
    tenant_id: int = DEFAULT_TENANT_ID,
) -> tuple[int, str, datetime] | None:
    """Return `(user_id, jti, expires_at)` on valid JWT; None otherwise.

    Resolution order:

    1. Parse the JWT header without verifying.
    2. If `kid` is absent or `env-legacy`, delegate to sync `verify_jwt`
       (legacy HS256 + SECRET_KEY).
    3. Otherwise resolve `kid` → key row. Reject if missing or RETIRED.
    4. Reject if the row's `tenant_id` doesn't match the caller's
       `tenant_id` (forged-kid attack).
    5. Verify with the row's algorithm + material. ACTIVE + RETIRING
       rows both pass (grace window).
    """
    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError:
        return None
    kid = header.get("kid")
    if kid in (None, ENV_LEGACY_KID):
        # The env-legacy DB row carries the same `SECRET_KEY` material as
        # the sync verifier; reusing that path skips one DB roundtrip.
        return verify_jwt(token)

    key = await _get_signing_key_by_kid(session, kid=kid)
    if key is None or key.status == TenantSigningKeyStatus.RETIRED:
        return None
    if key.tenant_id != tenant_id:
        return None

    try:
        decoded = jwt.decode(
            token,
            _verification_material(key),
            algorithms=[key.algorithm.value],
        )
        sub = decoded.get("sub")
        jti = decoded.get("jti")
        exp = decoded.get("exp")
        if sub is None or not jti or exp is None:
            return None
        return int(sub), str(jti), datetime.fromtimestamp(int(exp), tz=UTC)
    except (jwt.InvalidTokenError, ValueError):
        return None


# ── JWT denylist (plan 50 / 0.2.1.04) ────────────────────────────────────


async def revoke_jwt(
    session: AsyncSession,
    *,
    jti: str,
    user_id: int,
    expires_at: datetime,
) -> None:
    """Insert a row into `revoked_jwt`. Idempotent on duplicate `jti`."""
    existing = await session.exec(select(RevokedJwt.id).where(RevokedJwt.jti == jti))
    if existing.one_or_none() is not None:
        return
    session.add(
        RevokedJwt(
            jti=jti,
            user_id=user_id,
            revoked_at=datetime.now(UTC),
            expires_at=expires_at,
        )
    )
    await session.flush()


async def is_jwt_revoked(session: AsyncSession, *, jti: str) -> bool:
    """O(1) lookup on the `jti` unique index. True iff a revocation row exists."""
    stmt = select(RevokedJwt.id).where(RevokedJwt.jti == jti)
    result = await session.exec(stmt)
    return result.one_or_none() is not None


async def cleanup_expired_revoked_jwts(session: AsyncSession) -> int:
    """Delete `revoked_jwt` rows whose `expires_at` has passed. Returns count."""
    now = datetime.now(UTC)
    stmt = delete(RevokedJwt).where(RevokedJwt.expires_at < now)
    result = await session.execute(stmt)
    return int(result.rowcount or 0)
