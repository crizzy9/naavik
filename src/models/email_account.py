"""EmailAccount entity — per-user IMAP inbox connection (plan 90 / 0.5.0.01).

The `imap_password` column holds a Fernet ciphertext token, not plaintext
(plan 90 § A.2.a — OWNER-APPROVED 2026-06-25). Encrypt/decrypt lives behind the
`services/email_credentials.py` seam; the column type is unchanged (the token is
urlsafe-base64 ASCII) so no migration is required. Trust posture = trust the DB
column + SECRET_KEY, same as JWT signing.

Per `AGENTS.md § Key Conventions § CLI` this is distinct from the deleted vault:
no `~/.naavik/*.enc` file, no key.bin, no audit log, no CLI — just a DB column
cipher.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Index, UniqueConstraint
from sqlmodel import Field, SQLModel

from ._common import utcnow
from .enums import EmailAccountProvider, EmailAccountStatus


class EmailAccount(SQLModel, table=True):
    __tablename__ = "email_account"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "provider",
            "account_email",
            name="uq_email_account_user_provider_email",
        ),
        Index(
            "ix_email_account_user_status",
            "user_id",
            "status",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", ondelete="CASCADE", index=True)

    provider: EmailAccountProvider = Field(default=EmailAccountProvider.IMAP)
    account_email: str

    imap_host: str
    imap_port: int = Field(default=993)
    imap_username: str
    # Fernet ciphertext token (plan 90 § A.2.a, OWNER-APPROVED 2026-06-25) — write
    # via `email_credentials.store_imap_password`, read via `load_imap_password`.
    # Never construct/read the raw value directly outside that seam.
    imap_password: str
    imap_use_tls: bool = Field(default=True)

    status: EmailAccountStatus = Field(default=EmailAccountStatus.OK)
    last_sync_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    last_synced_uid: str | None = None
    connection_failure_count: int = Field(default=0)
    last_error_message: str | None = None
    # Plan 95 § 3.9.1 — per-account opt-in (default OFF): sync persists a
    # 2,000-char plaintext body excerpt on new mail and the classifier uses
    # it instead of the 240-char snippet. Explicitly widens the at-rest
    # privacy surface; the owner flips it in Settings → Email.
    store_body_excerpt: bool = Field(default=False)

    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    deleted_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
