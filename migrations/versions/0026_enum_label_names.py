"""Rename Postgres enum labels to member NAMES — runtime enum fix.

Revision ID: 0026_enum_label_names
Revises: 0025_fk_ondelete_rules
Create Date: 2026-07-02

SQLAlchemy's `sa.Enum(PyEnum)` persists (and binds parameters as) the Python
member **name**, not its value. Most Naavik enums use NAME == value, so their
Postgres types (whose labels equal the names) work. Four types were created
from lowercase **values** instead, so every bind against them fails at
runtime with `invalid input value for enum ...`:

- `closedreason` (0001-era) — closing/archiving an application with a reason
  raised on live Postgres (`'USER_ARCHIVED'::closedreason` → error).
- `emailaccountprovider`, `emailaccountstatus`, `unclassifiedreason` (0024) —
  the email-sync cron crashed every 10 minutes on
  `WHERE status != 'DISABLED'`, and no EmailAccount row could be inserted.
- `appeventkind` label `email_status_suggested` (0024's ADD VALUE) — the
  human-confirm suggestion seam could not write its audit event.

Fix: rename each mismatched label to the member name. `ALTER TYPE ... RENAME
VALUE` rewrites the label in place, so existing rows (if any) follow
automatically and SQLAlchemy round-trips members transparently — Python-side
`.value` strings (used by templates/JSON) are untouched.

Renames are conditional on the old label existing, so the migration converges
whether the type was created lowercase (fresh replay of 0001/0022/0024) or
already fixed. Postgres-only; SQLite stores enum names as VARCHAR already.
Reversible: downgrade restores the historical lowercase labels.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0026_enum_label_names"
down_revision: str | None = "0025_fk_ondelete_rules"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (enum type, old label == Python .value, new label == Python .name)
_RENAMES: list[tuple[str, str, str]] = [
    ("closedreason", "rejected_by_them", "REJECTED_BY_THEM"),
    ("closedreason", "withdrawn_by_me", "WITHDRAWN_BY_ME"),
    ("closedreason", "ghosted", "GHOSTED"),
    ("closedreason", "accepted_other", "ACCEPTED_OTHER"),
    ("closedreason", "user_archived", "USER_ARCHIVED"),
    ("emailaccountprovider", "imap", "IMAP"),
    ("emailaccountprovider", "gmail", "GMAIL"),
    ("emailaccountprovider", "outlook", "OUTLOOK"),
    ("emailaccountstatus", "ok", "OK"),
    ("emailaccountstatus", "auth_required", "AUTH_REQUIRED"),
    ("emailaccountstatus", "rate_limited", "RATE_LIMITED"),
    ("emailaccountstatus", "disabled", "DISABLED"),
    ("unclassifiedreason", "no_provider_configured", "NO_PROVIDER_CONFIGURED"),
    ("unclassifiedreason", "llm_failed", "LLM_FAILED"),
    ("unclassifiedreason", "rate_limited", "RATE_LIMITED"),
    ("unclassifiedreason", "cost_cap_exhausted", "COST_CAP_EXHAUSTED"),
    ("appeventkind", "email_status_suggested", "EMAIL_STATUS_SUGGESTED"),
    # SigningAlgorithm.EDDSA carries value "EdDSA" — same class of bug,
    # latent (EdDSA keys are reserved for future; HS256 is the default).
    ("signingalgorithm", "EdDSA", "EDDSA"),
]


def _rename(type_name: str, old: str, new: str) -> str:
    # RENAME VALUE has no IF EXISTS; guard via catalog lookup so the
    # migration converges from either label state. The `new`-absence guard
    # matters on fresh installs where 0001 already created the type with
    # NAME labels from live metadata (renaming onto an existing label is a
    # DuplicateObject error).
    return f"""
    DO $$
    BEGIN
        IF EXISTS (
            SELECT 1 FROM pg_enum e
            JOIN pg_type t ON t.oid = e.enumtypid
            WHERE t.typname = '{type_name}' AND e.enumlabel = '{old}'
        ) AND NOT EXISTS (
            SELECT 1 FROM pg_enum e
            JOIN pg_type t ON t.oid = e.enumtypid
            WHERE t.typname = '{type_name}' AND e.enumlabel = '{new}'
        ) THEN
            ALTER TYPE {type_name} RENAME VALUE '{old}' TO '{new}';
        END IF;
    END $$;
    """


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for type_name, old, new in _RENAMES:
        op.execute(_rename(type_name, old, new))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for type_name, old, new in _RENAMES:
        op.execute(_rename(type_name, new, old))
