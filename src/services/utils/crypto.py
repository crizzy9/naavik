"""Shared SECRET_KEY-derived Fernet helper (plan 91 5.4).

One place for the symmetric-encryption primitive that was copied verbatim
into `email_credentials` and `calendar_sync`. Derives a stable 32-byte key
from `SECRET_KEY` via SHA-256 — the same SECRET_KEY trust posture as JWT
signing (plan 26 retrospective; explicitly NOT a vault revival — see the
vault sunset, plan 26 / task 2.12).
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet

from config import settings as app_settings


def secret_key_fernet() -> Fernet:
    """Fernet keyed off SECRET_KEY. Rotating SECRET_KEY invalidates all
    ciphertexts — callers must fail closed (return None / needs-reconnect),
    never fall back to raw column values."""
    digest = hashlib.sha256(app_settings.secret_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))
