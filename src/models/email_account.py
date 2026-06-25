"""EmailAccount entity — per-user IMAP inbox connection (plan 90 / 0.5.0.01).

PLAINTEXT password column by manager directive (manager override on plan § A.2 Q2:
the plan recommended Fernet column-level encryption [A.2.a]; manager pivoted to
A.2.b plaintext-DB because Fernet's key would derive from `SECRET_KEY` — the same
trust posture the owner killed the vault over [plan 26]). The credential read/write
seam lives in `services/email_credentials.py`; a Fernet swap is a ~10-LOC change
inside that module if owner opts in at PR review.

Per `AGENTS.md § Key Conventions § CLI` no new vault / `~/.naavik/*.enc` artifact
is introduced.
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
    user_id: int = Field(foreign_key="user.id", index=True)

    provider: EmailAccountProvider = Field(default=EmailAccountProvider.IMAP)
    account_email: str

    imap_host: str
    imap_port: int = Field(default=993)
    imap_username: str
    # PLAINTEXT by manager directive — Fernet column-encryption (plan 90 § A.2.a)
    # is the owner-gated Q2 opt-in; the interface in `services/email_credentials.py`
    # makes that a ~10-LOC swap. Do NOT add SECRET_KEY-derived encryption without
    # explicit owner sign-off (vault sunset, AGENTS.md § Key Conventions § CLI).
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
