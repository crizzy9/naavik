"""Auth service — bcrypt + JWT cookie + CSRF + brute-force rate limit.

Plan 91 Phase 4.1 split the former `services/auth.py` god-module into
`passwords` / `tokens` / `csrf` / `throttle` / `users`; this package facade
re-exports every name (including the private helpers the test suite
touches) so all 24 importers and every `services.auth.*` patch target keep
resolving unchanged. The FastAPI deps (`get_current_user`,
`require_password_complete`, `require_authed_session`) moved to
`src/api/deps.py` — that fixes the service-layer `from ui.auth_stub import`
violation — and are re-exported lazily below (PEP 562) to avoid the
services↔api import cycle.

Per BACKEND.md § D.1, § G + plan 10 § B.3, with plan 62 (0.2.7.07) layered
on for multi-tenant JWT signing-key rotation. Canonical rotation reference:
`docs/design/JWT_ROTATION.md`.
"""

from __future__ import annotations

from typing import Any

from .csrf import (
    CSRF_COOKIE,
    issue_csrf_token,
    validate_csrf,
)
from .passwords import (
    PASSWORD_MIN_LENGTH,
    hash_password,
    hash_password_with_complexity_check,
    validate_password_complexity,
    verify_password,
)
from .passwords import _bcrypt_cost as _bcrypt_cost
from .throttle import _LOGIN_ATTEMPT_THRESHOLD as _LOGIN_ATTEMPT_THRESHOLD
from .throttle import _LOGIN_ATTEMPT_WINDOW as _LOGIN_ATTEMPT_WINDOW
from .throttle import _login_attempts as _login_attempts
from .throttle import (
    get_client_ip,
    is_rate_limited,
    record_login_attempt,
    reset_rate_limit,
)
from .tokens import (
    DEFAULT_TENANT_ID,
    ENV_LEGACY_KID,
    JWT_ALGORITHM,
    JWT_TTL_DEFAULT,
    JWT_TTL_KEEP_SIGNED_IN,
    SESSION_COOKIE,
    cleanup_expired_revoked_jwts,
    is_jwt_revoked,
    issue_jwt,
    issue_jwt_async,
    revoke_jwt,
    verify_jwt,
    verify_jwt_async,
)
from .tokens import _get_active_signing_key as _get_active_signing_key
from .tokens import _get_signing_key_by_kid as _get_signing_key_by_kid
from .tokens import _signing_material as _signing_material
from .tokens import _verification_material as _verification_material
from .users import (
    authenticate,
    get_user,
    get_user_by_email,
    get_user_by_id,
)

# The FastAPI deps live in api/deps.py (delivery layer). Lazy re-export so
# `from services.auth import require_authed_session` keeps working for the
# 20+ route modules without creating an import cycle at package-load time.
_API_DEPS = frozenset({"get_current_user", "require_password_complete", "require_authed_session"})


def __getattr__(name: str) -> Any:
    if name in _API_DEPS:
        from api import deps as _deps

        return getattr(_deps, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "CSRF_COOKIE",
    "DEFAULT_TENANT_ID",
    "ENV_LEGACY_KID",
    "JWT_ALGORITHM",
    "JWT_TTL_DEFAULT",
    "JWT_TTL_KEEP_SIGNED_IN",
    "PASSWORD_MIN_LENGTH",
    "SESSION_COOKIE",
    "authenticate",
    "cleanup_expired_revoked_jwts",
    "get_client_ip",
    "get_current_user",
    "get_user",
    "get_user_by_email",
    "get_user_by_id",
    "hash_password",
    "hash_password_with_complexity_check",
    "is_jwt_revoked",
    "is_rate_limited",
    "issue_csrf_token",
    "issue_jwt",
    "issue_jwt_async",
    "record_login_attempt",
    "require_authed_session",
    "require_password_complete",
    "reset_rate_limit",
    "revoke_jwt",
    "validate_csrf",
    "validate_password_complexity",
    "verify_jwt",
    "verify_jwt_async",
    "verify_password",
]
