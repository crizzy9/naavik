"""CSRF double-submit token helpers.

Split out of the auth god-module in plan 91 Phase 4.1; behaviour unchanged.

Server stores the token in a non-HttpOnly cookie; client mirrors via
`X-CSRF-Token` header. Validated on every state-changing request. Rotated
on auth events (login / logout / password change).
"""

from __future__ import annotations

import secrets

CSRF_COOKIE = "naavik_csrf"


def issue_csrf_token() -> str:
    """Generate a fresh CSRF token (URL-safe, 32 bytes)."""
    return secrets.token_urlsafe(32)


def validate_csrf(cookie_token: str | None, header_token: str | None) -> bool:
    """Constant-time double-submit comparison."""
    if not cookie_token or not header_token:
        return False
    return secrets.compare_digest(cookie_token, header_token)
