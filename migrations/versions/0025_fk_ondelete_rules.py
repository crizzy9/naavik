"""FK ON DELETE rules — referential-integrity hardening.

Revision ID: 0025_fk_ondelete_rules
Revises: 0024_email_account_message
Create Date: 2026-07-01

Every user-scoped foreign key previously relied on Postgres's default
`NO ACTION`, which left orphan rows undefined on parent deletion and blocked
clean account/profile/application deletion. This migration makes the rules
explicit:

- **CASCADE** for owned children (non-null FKs): deleting a User removes their
  Settings / Profile / Jobs / Applications / Contacts / …; deleting a Profile
  removes its Experiences / Bullets / Skills / …; deleting an Application
  removes its GeneratedDocuments / ScreenerAnswers / links.
- **SET NULL** for nullable informational cross-references: an Application
  keeps its snapshot when its Job is deleted; a Job's `warm_intro_contact_id`
  / `last_scrape_run_id` null out when the referent is removed; email/outreach
  rows keep their history when a linked Application is removed.

The rule mirrors the model layer (`Field(..., ondelete=...)`): nullable →
SET NULL, non-null → CASCADE. Applied by discovering each FK's real constraint
name from the catalog and recreating it (constraint names are auto-generated
and differ across environments, so we never hardcode them).

Postgres-only. On SQLite (the service-test backend) this is a no-op: SQLite
can't `ALTER ... DROP CONSTRAINT`, and fresh SQLite schemas already emit the
ondelete rules from the model DDL. Reversible: downgrade restores NO ACTION.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025_fk_ondelete_rules"
down_revision: str | None = "0024_email_account_message"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (table, column, ref_table, ref_column, ondelete)
_FKS: list[tuple[str, str, str, str, str]] = [
    # ── CASCADE: owned children ────────────────────────────────────────
    ("settings", "user_id", "user", "id", "CASCADE"),
    ("profile", "user_id", "user", "id", "CASCADE"),
    ("profile_embedding", "user_id", "user", "id", "CASCADE"),
    ("revoked_jwt", "user_id", "user", "id", "CASCADE"),
    ("job", "user_id", "user", "id", "CASCADE"),
    ("job_scrape_run", "user_id", "user", "id", "CASCADE"),
    ("job_embedding", "user_id", "user", "id", "CASCADE"),
    ("job_embedding", "job_id", "job", "id", "CASCADE"),
    ("application", "user_id", "user", "id", "CASCADE"),
    ("ats_credential", "user_id", "user", "id", "CASCADE"),
    ("app_event", "user_id", "user", "id", "CASCADE"),
    ("api_usage", "user_id", "user", "id", "CASCADE"),
    ("profile_answer", "user_id", "user", "id", "CASCADE"),
    ("contact", "user_id", "user", "id", "CASCADE"),
    ("outreach_message", "user_id", "user", "id", "CASCADE"),
    ("email_thread", "user_id", "user", "id", "CASCADE"),
    ("email_message", "user_id", "user", "id", "CASCADE"),
    ("email_account", "user_id", "user", "id", "CASCADE"),
    ("experience", "profile_id", "profile", "id", "CASCADE"),
    ("skill", "profile_id", "profile", "id", "CASCADE"),
    ("education", "profile_id", "profile", "id", "CASCADE"),
    ("project", "profile_id", "profile", "id", "CASCADE"),
    ("certification", "profile_id", "profile", "id", "CASCADE"),
    ("bullet", "experience_id", "experience", "id", "CASCADE"),
    ("generated_document", "application_id", "application", "id", "CASCADE"),
    ("application_screener_answer", "application_id", "application", "id", "CASCADE"),
    ("contact_application_link", "application_id", "application", "id", "CASCADE"),
    ("contact_application_link", "contact_id", "contact", "id", "CASCADE"),
    ("outreach_message", "contact_id", "contact", "id", "CASCADE"),
    ("email_message", "thread_id", "email_thread", "id", "CASCADE"),
    ("tenant_signing_key", "tenant_id", "tenant", "id", "CASCADE"),
    ("profile_answer", "source_screener_answer_id", "application_screener_answer", "id", "CASCADE"),
    # ── SET NULL: nullable informational cross-references ───────────────
    ("application", "job_id", "job", "id", "SET NULL"),
    ("job", "warm_intro_contact_id", "contact", "id", "SET NULL"),
    ("job", "last_scrape_run_id", "job_scrape_run", "id", "SET NULL"),
    ("outreach_message", "application_id", "application", "id", "SET NULL"),
    ("app_event", "application_id", "application", "id", "SET NULL"),
    ("api_usage", "application_id", "application", "id", "SET NULL"),
    ("email_thread", "application_id", "application", "id", "SET NULL"),
    ("email_thread", "contact_id", "contact", "id", "SET NULL"),
    ("email_message", "application_id", "application", "id", "SET NULL"),
    ("email_message", "account_id", "email_account", "id", "SET NULL"),
]


def _fk_name(table: str, column: str) -> str:
    """Deterministic FK name kept within Postgres's 63-char identifier cap."""
    name = f"fk_{table}_{column}"
    return name[:63]


def _existing_fk_names(bind, table: str, column: str) -> list[str]:
    """Return constraint names of FKs on `table.column` (Postgres catalog)."""
    rows = bind.execute(
        sa.text(
            """
            SELECT tc.constraint_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_name = :table
              AND kcu.column_name = :column
            """
        ),
        {"table": table, "column": column},
    )
    return [r[0] for r in rows]


def _recreate(bind, table, column, ref_table, ref_column, ondelete) -> None:
    for name in _existing_fk_names(bind, table, column):
        op.drop_constraint(name, table, type_="foreignkey")
    new_name = _fk_name(table, column)
    op.create_foreign_key(
        new_name,
        table,
        ref_table,
        [column],
        [ref_column],
        ondelete=ondelete,
    )


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # SQLite: fresh schema already carries ondelete from model DDL.
    for table, column, ref_table, ref_column, ondelete in _FKS:
        _recreate(bind, table, column, ref_table, ref_column, ondelete)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    # Restore NO ACTION (default) by recreating each FK without ondelete.
    for table, column, ref_table, ref_column, _ondelete in _FKS:
        for name in _existing_fk_names(bind, table, column):
            op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(
            _fk_name(table, column),
            table,
            ref_table,
            [column],
            [ref_column],
        )
