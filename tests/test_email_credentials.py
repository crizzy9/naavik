"""Plaintext credential-store seam (plan 90 / 0.5.0.01).

Manager-override Q2 lock: plaintext-DB option behind the credential-store
interface. These tests pin the plaintext passthrough — a future Fernet swap
will rewrite both functions; this file's expectations document the current
trust posture.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("NAAVIK_DEBUG", "1")

pytestmark = pytest.mark.uses_sample_data_shims


def test_store_and_load_round_trip():
    from models import EmailAccount
    from models.enums import EmailAccountProvider
    from services import email_credentials

    account = EmailAccount(
        user_id=1,
        provider=EmailAccountProvider.IMAP,
        account_email="a@example.com",
        imap_host="imap.example.com",
        imap_username="a@example.com",
        imap_password="",
    )
    email_credentials.store_imap_password(account, "p@ssw0rd-2026")
    # Plaintext seam: column carries the raw string today.
    assert account.imap_password == "p@ssw0rd-2026"
    assert email_credentials.load_imap_password(account) == "p@ssw0rd-2026"


def test_no_secret_key_derived_helper_present():
    """Vault-sunset guard: this module must NOT import `cryptography.fernet`
    or derive any key from `SECRET_KEY`. Owner-opt-in pivot replaces the two
    functions; until then the trust posture is plaintext.
    """
    import inspect

    from services import email_credentials

    src = inspect.getsource(email_credentials)
    forbidden_call_patterns = (
        "from cryptography",
        "import cryptography",
        "Fernet(",
        "fernet.encrypt",
        "fernet.decrypt",
        "settings.secret_key",
        "app_settings.secret_key",
    )
    for pat in forbidden_call_patterns:
        assert pat not in src, (
            f"{pat!r} found in services/email_credentials.py — vault sunset (plan 26 / "
            "AGENTS.md § Key Conventions § CLI) requires explicit owner sign-off"
        )
