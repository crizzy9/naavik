"""Fernet credential-store security contract (plan 90 / 0.5.0.01).

Q2 = Fernet column-level encryption (A.2.a), OWNER-APPROVED 2026-06-25. These
tests pin the security contract: a store/load round-trip recovers the original
password; the persisted column value is ciphertext (not the plaintext); and a
token encrypted under one SECRET_KEY fails closed (returns None, never garbage)
when SECRET_KEY rotates.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("NAAVIK_DEBUG", "1")

pytestmark = pytest.mark.uses_sample_data_shims


def _account(password_column: str = ""):
    from models import EmailAccount
    from models.enums import EmailAccountProvider

    return EmailAccount(
        user_id=1,
        provider=EmailAccountProvider.IMAP,
        account_email="a@example.com",
        imap_host="imap.example.com",
        imap_username="a@example.com",
        imap_password=password_column,
    )


def test_store_and_load_round_trip():
    from services.email import credentials as email_credentials

    account = _account()
    email_credentials.store_imap_password(account, "p@ssw0rd-2026")
    assert email_credentials.load_imap_password(account) == "p@ssw0rd-2026"


def test_ciphertext_at_rest():
    """The value persisted in the column is ciphertext — not the plaintext, and
    does not contain it (DB dump / pg_dump does not leak the password verbatim)."""
    from services.email import credentials as email_credentials

    secret = "p@ssw0rd-2026"
    account = _account()
    email_credentials.store_imap_password(account, secret)

    stored = account.imap_password
    assert stored != secret
    assert secret not in stored
    # Fernet tokens are urlsafe-base64 ASCII.
    assert stored.encode("ascii")


def test_wrong_secret_key_fails_closed(monkeypatch):
    """A token encrypted under one SECRET_KEY must NOT decrypt under another.
    load_imap_password returns None (fail-closed), never garbage-as-password."""
    from config import settings as app_settings
    from services.email import credentials as email_credentials

    account = _account()
    email_credentials.store_imap_password(account, "p@ssw0rd-2026")

    monkeypatch.setattr(app_settings, "secret_key", "a-totally-different-secret-key-0001")
    assert email_credentials.load_imap_password(account) is None


def test_load_empty_column_returns_none():
    """A never-stored credential (empty column) fails closed rather than feeding
    an empty string to the IMAP client."""
    from services.email import credentials as email_credentials

    assert email_credentials.load_imap_password(_account(password_column="")) is None


def test_plaintext_column_value_does_not_decrypt():
    """A raw plaintext value in the column (not a Fernet token) fails closed —
    load never returns the ciphertext/plaintext column as the password."""
    from services.email import credentials as email_credentials

    account = _account(password_column="not-a-fernet-token")
    assert email_credentials.load_imap_password(account) is None
