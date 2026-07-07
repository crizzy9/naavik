"""Full-body handling — plan 95 slice 95l (the 0.5.0.05a opt-in, folded in).

Revision ID: 0045_full_body_optin
Revises: 0044_staleness_settings
Create Date: 2026-07-07

- `email_message.imap_uid` — persisted so the on-demand body route can
  BODY.PEEK the full text without storing it (NULL for pre-95l mail; the
  chain falls back to the provider deep-link).
- `email_message.body_excerpt` — opt-in 2,000-char plaintext excerpt.
- `email_account.store_body_excerpt` — the per-account toggle, default OFF
  (the at-rest privacy default stays snippet-only).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0045_full_body_optin"
down_revision = "0044_staleness_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "email_message",
        sa.Column("imap_uid", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "email_message",
        sa.Column("body_excerpt", sa.String(length=2000), nullable=True),
    )
    op.add_column(
        "email_account",
        sa.Column("store_body_excerpt", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("email_account", "store_body_excerpt")
    op.drop_column("email_message", "body_excerpt")
    op.drop_column("email_message", "imap_uid")
