"""Password hashing + complexity rules (bcrypt).

Split out of the auth god-module in plan 91 Phase 4.1; behaviour unchanged.

- bcrypt cost=12 in production; cost=4 for tests via `NAAVIK_BCRYPT_COST`
  env override (plan 10 Q5).
"""

from __future__ import annotations

import os

import bcrypt

# ── Password complexity (plan 18 / PC.6) ─────────────────────────────────

# Plan 0.7.0.48 Wave 2 (2026-05-25): 12 → 8 chars. 8 is the standard
# self-hosted-app baseline; 12 was over-tuned for the original cloud framing.
PASSWORD_MIN_LENGTH = 8


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
