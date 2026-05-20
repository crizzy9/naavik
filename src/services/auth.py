"""Auth service — bcrypt + JWT cookie + CSRF + brute-force rate limit.

Per BACKEND.md § D.1, § G + plan 10 § B.3.

- bcrypt cost=12 in production; cost=4 for tests via `NAAVIK_BCRYPT_COST`
  env override (plan 10 Q5).
- JWT HS256 signed with `Settings.secret_key`. Single signing key — multi-key
  rotation deferred to Phase 2+ (plan 10 Q7).
- Cookie flags: `HttpOnly` + `Secure` (relaxed only when `Settings.debug` for
  local dev) + `SameSite=Strict` + `Path=/`.
- CSRF: double-submit pattern. Server stores token in a non-HttpOnly cookie;
  client mirrors via `X-CSRF-Token` header. Validated on every state-changing
  request. Rotated on auth events (login / logout / password change).
- Brute-force guard: in-memory rate limiter (5 fails / 15min per IP) returns
  429.
"""

from __future__ import annotations

import os
import secrets
from collections import deque
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from config import settings as app_settings
from db.session import get_session
from models import RevokedJwt, Settings, User

# ── Constants ───────────────────────────────────────────────────────────

SESSION_COOKIE = "naavik_session"
CSRF_COOKIE = "naavik_csrf"
JWT_ALGORITHM = "HS256"
JWT_TTL_DEFAULT = timedelta(hours=24)
JWT_TTL_KEEP_SIGNED_IN = timedelta(days=30)

_LOGIN_ATTEMPT_WINDOW = timedelta(minutes=15)
_LOGIN_ATTEMPT_THRESHOLD = 5

# Rate-limiter state: ip → deque[timestamps]. In-process, single-instance MVP.
_login_attempts: dict[str, deque[datetime]] = {}


# ── Password complexity (plan 18 / PC.6) ─────────────────────────────────

PASSWORD_MIN_LENGTH = 12


def validate_password_complexity(plain: str) -> str | None:
    """Return None if `plain` meets PC.6 rules; else a user-facing message.

    Stop-at-first-violation order: empty → length → letter → digit. Caller
    renders the returned string in the `_login_error_card` HTMX swap.
    Constant-time-ness not relevant — runs on operator-typed plaintext, not
    on a credential that could leak via timing.
    """
    if not plain:
        return "Password must not be empty."
    if len(plain) < PASSWORD_MIN_LENGTH:
        return f"Password must be at least {PASSWORD_MIN_LENGTH} characters."
    if not any("a" <= c.lower() <= "z" for c in plain):
        return "Password must contain at least one letter (a-z)."
    if not any("0" <= c <= "9" for c in plain):
        return "Password must contain at least one digit (0-9)."
    return None


# ── Password hashing ─────────────────────────────────────────────────────


def _bcrypt_cost() -> int:
    """Return bcrypt rounds — 4 in tests via env override; 12 prod default."""
    raw = os.environ.get("NAAVIK_BCRYPT_COST")
    if raw:
        try:
            cost = int(raw)
            if 4 <= cost <= 14:
                return cost
        except ValueError:
            pass
    return 12


def hash_password(plain: str) -> str:
    """bcrypt-hash a plaintext password. Cost configurable via env."""
    if not plain:
        raise ValueError("password must not be empty")
    salt = bcrypt.gensalt(rounds=_bcrypt_cost())
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")


def hash_password_with_complexity_check(plain: str) -> str:
    """`hash_password` after validating PC.6 complexity. Canonical entry
    point for plaintext-entry auth routes; bare `hash_password` is reserved
    for seed (which generates passwords that satisfy the rules by
    construction) and tests that need to inject known weak hashes.
    """
    err = validate_password_complexity(plain)
    if err is not None:
        raise ValueError(err)
    return hash_password(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True iff `plain` matches the bcrypt hash. Rejects empty input."""
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ── JWT ──────────────────────────────────────────────────────────────────


def issue_jwt(user_id: int, *, keep_signed_in: bool = False) -> str:
    """Issue a fresh signed JWT carrying `user_id` + a per-issue `jti`."""
    ttl = JWT_TTL_KEEP_SIGNED_IN if keep_signed_in else JWT_TTL_DEFAULT
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "jti": secrets.token_urlsafe(16),
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
    }
    return jwt.encode(payload, app_settings.secret_key, algorithm=JWT_ALGORITHM)


def verify_jwt(token: str) -> tuple[int, str, datetime] | None:
    """Return `(user_id, jti, expires_at)` on valid JWT; None on expired/invalid.

    Plan 50 (0.2.1.04): expanded from `int | None` to a tuple so callers
    can drive the `RevokedJwt` denylist check + persist `expires_at`
    when revoking the current token at password-change time.
    """
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


# ── CSRF ─────────────────────────────────────────────────────────────────


def issue_csrf_token() -> str:
    """Generate a fresh CSRF token (URL-safe, 32 bytes)."""
    return secrets.token_urlsafe(32)


def validate_csrf(cookie_token: str | None, header_token: str | None) -> bool:
    """Constant-time double-submit comparison."""
    if not cookie_token or not header_token:
        return False
    return secrets.compare_digest(cookie_token, header_token)


# ── Brute-force guard ────────────────────────────────────────────────────


def record_login_attempt(ip: str, *, success: bool) -> None:
    """Track a login attempt. On success, clear the IP's failure window."""
    if success:
        _login_attempts.pop(ip, None)
        return
    now = datetime.now(UTC)
    bucket = _login_attempts.setdefault(ip, deque())
    bucket.append(now)
    cutoff = now - _LOGIN_ATTEMPT_WINDOW
    while bucket and bucket[0] < cutoff:
        bucket.popleft()


def is_rate_limited(ip: str) -> bool:
    """Return True if the IP exceeded the failure threshold within the window."""
    bucket = _login_attempts.get(ip)
    if not bucket:
        return False
    cutoff = datetime.now(UTC) - _LOGIN_ATTEMPT_WINDOW
    while bucket and bucket[0] < cutoff:
        bucket.popleft()
    return len(bucket) >= _LOGIN_ATTEMPT_THRESHOLD


def reset_rate_limit(ip: str | None = None) -> None:
    """Test helper — clear rate-limit state."""
    if ip is None:
        _login_attempts.clear()
    else:
        _login_attempts.pop(ip, None)


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


# ── DB helpers ───────────────────────────────────────────────────────────


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    """Fetch a non-deleted active user by email, case-folded."""
    norm = email.strip().lower()
    stmt = select(User).where(
        User.email == norm,
        User.deleted_at.is_(None),
    )
    result = await session.exec(stmt)
    return result.one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    stmt = select(User).where(User.id == user_id, User.deleted_at.is_(None))
    result = await session.exec(stmt)
    return result.one_or_none()


async def get_or_create_settings(session: AsyncSession, user_id: int) -> Settings:
    """Settings is a singleton per user — auto-create on first read."""
    stmt = select(Settings).where(Settings.user_id == user_id)
    result = await session.exec(stmt)
    row = result.one_or_none()
    if row is not None:
        return row
    row = Settings(user_id=user_id)
    session.add(row)
    await session.flush()
    return row


async def authenticate(
    session: AsyncSession,
    email: str,
    password: str,
) -> User | None:
    """Look up by email, verify bcrypt hash. Constant time even on miss
    (bcrypt over a dummy hash) so timing leaks don't reveal valid emails."""
    user = await get_user_by_email(session, email)
    # Always run bcrypt to keep timing constant.
    if user is None:
        verify_password(password, "$2b$12$placeholder.dummy.hash.invalid........")
        return None
    if not verify_password(password, user.password_hash):
        return None
    if not user.is_active:
        return None
    return user


# ── FastAPI dependency ───────────────────────────────────────────────────


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
    naavik_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> User:
    """Resolve the user via JWT cookie. Raise 401 on missing/invalid."""
    if not naavik_session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    result = verify_jwt(naavik_session)
    if result is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    user_id, jti, _ = result
    if await is_jwt_revoked(session, jti=jti):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session revoked")
    user = await get_user_by_id(session, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account disabled")
    return user


async def require_password_complete(
    user: User = Depends(get_current_user),
) -> User:
    """Like `get_current_user`, but raises 303 with HX-Redirect when the
    user must change their password. Wrap every authed route except the
    change-password page + endpoint with this.

    Plan 18 (PC.6, 2026-05-17). Use `get_current_user` directly only for
    the /auth/change-password page + POST /api/v1/auth/change-password +
    POST /api/v1/auth/logout + GET /api/v1/auth/me. Every other authed
    route uses this.
    """
    if user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            detail="Password change required.",
            headers={
                "HX-Redirect": "/auth/change-password",
                "Location": "/auth/change-password",
            },
        )
    return user


async def require_authed_session(
    request: Request,
    session: AsyncSession = Depends(get_session),
    naavik_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> User | None:
    """Transitional auth dep for the plan-09 fake-session substrate.

    Plan 23 (PC.6a, 2026-05-18). Gates state-changing UI + API routes whose
    callers still send the fake-session cookie (`naavik_session=fake-1`)
    rather than a real JWT. Retires when the fake-session stub is deleted
    (post-Phase-2 task 2.12 / a real-auth migration). At that time:
    `Depends(require_authed_session)` → `Depends(require_password_complete)`.
    Also tighten `_user: User | None` -> `User` on dependent handlers because
    `require_password_complete` returns `User`, not `User | None`.

    Resolution order:
      1. Missing cookie → 401.
      2. Cookie equals `FAKE_SESSION_VALUE` → return None. No user resolution.
      3. Otherwise treat as JWT. On invalid/expired → 401. On valid → look
         up the user; if `must_change_password` is True, raise:
           - 307 + `HX-Redirect: /auth/change-password` for UI paths
             (anything NOT prefixed with `/api/v1/`).
           - 403 with `{"detail": "must change password"}` for API paths
             (prefix `/api/v1/`). API consumers shouldn't auto-follow a
             redirect to an HTML page.

    Routes that USE this dep accept `_user: User | None` because the
    fake-session path returns None; the handler body keeps reading
    `sample_data` accessors the same way it does today.
    """
    # Import inside the function to keep the fake-session constant a
    # single source of truth and avoid a top-of-file circular import.
    from ui.auth_stub import FAKE_SESSION_VALUE

    if not naavik_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    if naavik_session == FAKE_SESSION_VALUE:
        return None

    result = verify_jwt(naavik_session)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired",
        )
    user_id, jti, _ = result
    if await is_jwt_revoked(session, jti=jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session revoked",
        )
    user = await get_user_by_id(session, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account disabled",
        )
    if user.must_change_password:
        # Path-based split per dispatch brief. `HX-Redirect` is set on
        # both branches so HTMX clients (which always set `HX-Request` and
        # may target either path) navigate the browser regardless. The
        # 403 vs 307 distinction matters for non-HTMX consumers (curl,
        # SDKs) that should not auto-follow a redirect to an HTML page.
        is_api = request.url.path.startswith("/api/v1/")
        if is_api:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="must change password",
                headers={"HX-Redirect": "/auth/change-password"},
            )
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            detail="Password change required.",
            headers={
                "HX-Redirect": "/auth/change-password",
                "Location": "/auth/change-password",
            },
        )
    return user


def get_client_ip(request: Request) -> str:
    """Return the request's client IP, honoring `X-Forwarded-For` if set
    (single-instance MVP — no chain validation)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"
