"""Email monitoring foundation tables — plan 90 (0.5.0.01).

Revision ID: 0024_email_account_message
Revises: 0023_profile_raw_resume_text
Create Date: 2026-06-25

Additive:
- `email_account` table (per-user IMAP inbox connection; the `imap_password`
  column holds a Fernet ciphertext token — keyed off `SECRET_KEY` via
  `services/email_credentials.py` (plan § A.2.a, owner-approved 2026-06-25).
  The column type is plain `str` because the token is ASCII; no schema change
  was needed for the encryption).
- `email_message` table (per-message metadata + 200-char snippet; classification
  + suggested_status surfaces).
- 3 new Postgres ENUM types (`emailaccountprovider`, `emailaccountstatus`,
  `unclassifiedreason`) created in-line via SQLAlchemy column type emission.
- 1 ENUM extension on `appeventkind` (adds `email_status_suggested` value)
  via `ALTER TYPE ... ADD VALUE` in an autocommit_block (mirrors plan 22 /
  0022 + plan 27 / 0005 + plan 78 / 0021 precedent).

Reversible (drops tables + 3 new enums in downgrade; pre-PG16 can't drop
the new appeventkind value — documented no-op consistent with sibling
migrations).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024_email_account_message"
down_revision: str | None = "0023_profile_raw_resume_text"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        # Fresh-install fix (2026-07-01): these three enums originally used
        # `create_type=True`, which made a clean `alembic upgrade head` from an
        # empty Postgres DB fail at this migration with
        # `type "emailaccountprovider" already exists` — the ENUM's implicit
        # before-create DDL and the table create both emitted `CREATE TYPE`,
        # and the chain stopped at 0021 (a `docker compose up` blocker on a
        # brand-new host). CI never caught it: the chain-replay test runs on
        # SQLite where enums compile to TEXT. Fix: `create_type=False` on the
        # column types + one idempotent `.create(..., checkfirst=True)` each,
        # so re-runs and shared-metadata registration can't double-create.
        provider_type: object = postgresql.ENUM(
            "imap",
            "gmail",
            "outlook",
            name="emailaccountprovider",
            create_type=False,
        )
        status_type: object = postgresql.ENUM(
            "ok",
            "auth_required",
            "rate_limited",
            "disabled",
            name="emailaccountstatus",
            create_type=False,
        )
        unclassified_reason_type: object = postgresql.ENUM(
            "no_provider_configured",
            "llm_failed",
            "rate_limited",
            "cost_cap_exhausted",
            name="unclassifiedreason",
            create_type=False,
        )
        for _enum in (provider_type, status_type, unclassified_reason_type):
            _enum.create(bind, checkfirst=True)
        classification_type: object = postgresql.ENUM(
            name="emailclassification",
            create_type=False,
        )
        application_status_type: object = postgresql.ENUM(
            name="applicationstatus",
            create_type=False,
        )
    else:
        provider_type = sa.String()
        status_type = sa.String()
        unclassified_reason_type = sa.String()
        classification_type = sa.String()
        application_status_type = sa.String()

    op.create_table(
        "email_account",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "provider",
            provider_type,
            nullable=False,
            server_default="imap",
        ),
        sa.Column("account_email", sa.String(), nullable=False),
        sa.Column("imap_host", sa.String(), nullable=False),
        sa.Column(
            "imap_port",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("993"),
        ),
        sa.Column("imap_username", sa.String(), nullable=False),
        sa.Column("imap_password", sa.String(), nullable=False),
        sa.Column(
            "imap_use_tls",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "status",
            status_type,
            nullable=False,
            server_default="ok",
        ),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_uid", sa.String(), nullable=True),
        sa.Column(
            "connection_failure_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("last_error_message", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "provider",
            "account_email",
            name="uq_email_account_user_provider_email",
        ),
    )
    op.create_index(
        "ix_email_account_user_id",
        "email_account",
        ["user_id"],
    )
    op.create_index(
        "ix_email_account_user_status",
        "email_account",
        ["user_id", "status"],
    )

    op.create_table(
        "email_message",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("thread_id", sa.Integer(), nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=True),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("message_id_external", sa.String(), nullable=False),
        sa.Column("sender_email", sa.String(), nullable=False),
        sa.Column("sender_name", sa.String(), nullable=True),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("snippet", sa.String(length=240), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "classification",
            classification_type,
            nullable=True,
        ),
        sa.Column(
            "auto_classified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("classification_model", sa.String(), nullable=True),
        sa.Column("classification_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "unclassified_reason",
            unclassified_reason_type,
            nullable=True,
        ),
        sa.Column("urgency", sa.String(), nullable=True),
        sa.Column(
            "suggested_status",
            application_status_type,
            nullable=True,
        ),
        sa.Column("suggested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suggestion_dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suggestion_applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["thread_id"], ["email_thread.id"]),
        sa.ForeignKeyConstraint(["application_id"], ["application.id"]),
        sa.ForeignKeyConstraint(["account_id"], ["email_account.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "thread_id",
            "message_id_external",
            name="uq_email_message_external",
        ),
    )
    op.create_index(
        "ix_email_message_user_id",
        "email_message",
        ["user_id"],
    )
    op.create_index(
        "ix_email_message_thread_id",
        "email_message",
        ["thread_id"],
    )
    op.create_index(
        "ix_email_message_application_id",
        "email_message",
        ["application_id"],
    )
    op.create_index(
        "ix_email_message_account_id",
        "email_message",
        ["account_id"],
    )
    op.create_index(
        "ix_email_message_received_at",
        "email_message",
        ["received_at"],
    )
    op.create_index(
        "ix_email_message_thread_received",
        "email_message",
        ["thread_id", "received_at"],
    )
    op.create_index(
        "ix_email_message_user_class_received",
        "email_message",
        ["user_id", "classification", "received_at"],
    )

    if is_postgres:
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE appeventkind ADD VALUE IF NOT EXISTS 'email_status_suggested'")


def downgrade() -> None:
    op.drop_index("ix_email_message_user_class_received", table_name="email_message")
    op.drop_index("ix_email_message_thread_received", table_name="email_message")
    op.drop_index("ix_email_message_received_at", table_name="email_message")
    op.drop_index("ix_email_message_account_id", table_name="email_message")
    op.drop_index("ix_email_message_application_id", table_name="email_message")
    op.drop_index("ix_email_message_thread_id", table_name="email_message")
    op.drop_index("ix_email_message_user_id", table_name="email_message")
    op.drop_table("email_message")

    op.drop_index("ix_email_account_user_status", table_name="email_account")
    op.drop_index("ix_email_account_user_id", table_name="email_account")
    op.drop_table("email_account")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS unclassifiedreason")
        op.execute("DROP TYPE IF EXISTS emailaccountstatus")
        op.execute("DROP TYPE IF EXISTS emailaccountprovider")
    # Pre-PG16 can't drop the new appeventkind value; documented no-op
    # consistent with plan 22 / 0022 + plan 78 / 0021 precedent.
