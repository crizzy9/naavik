"""Drop vault-derived columns from Settings.

Revision ID: 0004_drop_vault_cols
Revises: 0003_user_must_change_pw
Create Date: 2026-05-19

Plan 26 (0.2.0.01): vault deprecation. The five columns dropped here all
tracked vault-derived state — booleans flipped by `settings_service.update_*`
on vault writes, and a fingerprint that lets the UI show "key set" without
holding the key. Post-vault, secret presence is runtime-derived from env
vars via `services/env_secrets.py`; the columns are dead weight.

Downgrade restores the columns with their default values (False for the
booleans, NULL for the fingerprint). It does NOT restore prior values — the
vault is gone, so there's nothing to read back. Self-hosters needing the
previous schema would re-enter via Settings UI after rollback. This is
acceptable: downgrade is a recovery path for a botched 0.2.0 release,
not a routine operation.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_drop_vault_cols"
down_revision: str | None = "0003_user_must_change_pw"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("settings", "llm_api_key_fingerprint")
    op.drop_column("settings", "discord_webhook_configured")
    op.drop_column("settings", "telegram_bot_configured")
    op.drop_column("settings", "portfolio_webhook_configured")
    op.drop_column("settings", "scraper_proxy_configured")


def downgrade() -> None:
    op.add_column(
        "settings",
        sa.Column("llm_api_key_fingerprint", sa.String(), nullable=True),
    )
    op.add_column(
        "settings",
        sa.Column(
            "discord_webhook_configured",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "settings",
        sa.Column(
            "telegram_bot_configured",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "settings",
        sa.Column(
            "portfolio_webhook_configured",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "settings",
        sa.Column(
            "scraper_proxy_configured",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
