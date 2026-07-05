"""Login brute-force guard — IP-keyed in-memory failure window.

Split out of the auth god-module in plan 91 Phase 4.1; behaviour unchanged.
`_login_attempts` is process-wide singleton state (resets on restart); the
`services.auth` facade re-exports the bound names so there is exactly one
instance (cross-cutting rule §5).

The per-USER limiter lives in `services/rate_limit.py` — it ships FastAPI
deps and stays there so this package keeps zero delivery-layer imports.
"""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime, timedelta

from fastapi import Request

_LOGIN_ATTEMPT_WINDOW = timedelta(minutes=15)
_LOGIN_ATTEMPT_THRESHOLD = 5

# Rate-limiter state: ip → deque[timestamps]. In-process, single-instance MVP.
_login_attempts: dict[str, deque[datetime]] = {}


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


def get_client_ip(request: Request) -> str:
    """Return the request's client IP, honoring `X-Forwarded-For` if set
    (single-instance MVP — no chain validation)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"
