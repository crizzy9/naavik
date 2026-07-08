"""Scheduling assistant — plan 96 slice 96f.

Revision ID: 0048_scheduling_settings
Revises: 0047_email_invite
Create Date: 2026-07-08

- `settings.scheduling_timezone` — IANA zone for the free-slot engine.
  NULL = auto (follow the host's current timezone, like the owner's
  calendar follows the device — owner decision 2026-07-08).
- `settings.scheduling_window` — working-hours band "HH:MM-HH:MM"
  (default 10:00-18:00, owner decision 2026-07-08).
- `email_message.action_needed` — the classifier's scheduling-action
  extraction (none | send_availability | pick_slot | confirm_time),
  deterministically post-checked like `end_client`. Drives the
  "Needs scheduling" strip together with the reconciler's
  conversation-level `needs_scheduling` stamp.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0048_scheduling_settings"
down_revision = "0047_email_invite"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "settings",
        sa.Column("scheduling_timezone", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "settings",
        sa.Column(
            "scheduling_window",
            sa.String(length=11),
            nullable=False,
            server_default="10:00-18:00",
        ),
    )
    op.add_column(
        "email_message",
        sa.Column("action_needed", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("email_message", "action_needed")
    op.drop_column("settings", "scheduling_window")
    op.drop_column("settings", "scheduling_timezone")
