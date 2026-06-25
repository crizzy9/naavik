"""IMAP credential storage seam — plan 90 (0.5.0.01).

PLAINTEXT DB column today by manager directive on plan § A.2 (override on the
plan's Fernet recommendation). The interface here makes the eventual swap to
Fernet column-level encryption — or any other server-side encryption — a
single-module change rather than a leaky refactor across `email_sync` /
`email_classifier` / route handlers.

DO NOT add SECRET_KEY-derived encryption inside this module without explicit
owner sign-off. Vault sunset (plan 26, AGENTS.md § Key Conventions § CLI)
killed the file-blob AES-256-GCM pattern + audit-log + Argon2id CLI; a Fernet
column derived from `SECRET_KEY` has the same trust posture and re-introduces
the same "attacker with SECRET_KEY decrypts everything" failure mode the owner
called theater. The owner-controlled opt-in path is to replace this module's
two functions with their Fernet equivalents (~10 LOC).
"""

from __future__ import annotations

from models import EmailAccount


def store_imap_password(account: EmailAccount, password: str) -> None:
    """Persist `password` onto `account` so a subsequent sync can read it.

    Plaintext passthrough today. Owner-gated swap point — replace the
    assignment with the server-side encryption call when opting in.
    """
    account.imap_password = password


def load_imap_password(account: EmailAccount) -> str:
    """Return the IMAP password ready to hand to the IMAP client.

    Plaintext passthrough today. Owner-gated swap point — replace the
    return with the matching decryption call when opting in.
    """
    return account.imap_password
