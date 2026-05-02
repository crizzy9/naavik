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
from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from config import settings as app_settings
from db.session import get_session
from models import Settings, User

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
    """Issue a fresh signed JWT carrying `user_id`."""
    ttl = JWT_TTL_KEEP_SIGNED_IN if keep_signed_in else JWT_TTL_DEFAULT
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
    }
    return jwt.encode(payload, app_settings.secret_key, algorithm=JWT_ALGORITHM)


def verify_jwt(token: str) -> int | None:
    """Return `user_id` on valid JWT; None on expired/invalid."""
    try:
        decoded = jwt.decode(
            token,
            app_settings.secret_key,
            algorithms=[JWT_ALGORITHM],
        )
        sub = decoded.get("sub")
        if sub is None:
            return None
        return int(sub)
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
    user_id = verify_jwt(naavik_session)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    user = await get_user_by_id(session, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account disabled")
    return user


def get_client_ip(request: Request) -> str:
    """Return the request's client IP, honoring `X-Forwarded-For` if set
    (single-instance MVP — no chain validation)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"
