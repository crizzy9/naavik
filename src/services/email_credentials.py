"""IMAP credential storage seam — plan 90 (0.5.0.01).

Fernet column-level encryption (plan 90 § A.2.a) — OWNER-APPROVED 2026-06-25.
Key = SHA-256(SECRET_KEY); trust posture = trust the DB column + SECRET_KEY,
same as JWT signing. Distinct from the deleted vault (no .enc file, no key.bin,
no audit log, no CLI) per AGENTS.md § Key Conventions § CLI.

`store_imap_password` encrypts the plaintext into the `EmailAccount.imap_password`
column as a urlsafe-base64 Fernet token; `load_imap_password` decrypts it back.
A decrypt failure (e.g. SECRET_KEY rotated after the password was stored) returns
None — the caller flips the account to AUTH_REQUIRED so the operator re-pastes the
app-password, rather than crashing the sync cron. The decrypted plaintext never
leaves this module's decrypt path: never logged, never on a Read schema, never in
a response body.
"""

from __future__ import annotations

import logging

from cryptography.fernet import Fernet, InvalidToken

from models import EmailAccount
from services._crypto import secret_key_fernet

log = logging.getLogger(__name__)


def _fernet() -> Fernet:
    return secret_key_fernet()


def store_imap_password(account: EmailAccount, password: str) -> None:
    """Encrypt `password` and persist the ciphertext token onto `account`."""
    account.imap_password = _fernet().encrypt(password.encode("utf-8")).decode("ascii")


def load_imap_password(account: EmailAccount) -> str | None:
    """Decrypt the stored token for the IMAP client.

    Returns None (fail-closed) when the ciphertext cannot be decrypted — e.g.
    the column is empty or SECRET_KEY has rotated since the password was stored.
    Never returns the raw column value as a fallback.
    """
    token = account.imap_password
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken:
        log.warning(
            "email_credentials: decrypt failed for account_id=%s "
            "(SECRET_KEY rotated?); marking needs-reconnect",
            account.id,
        )
        return None
