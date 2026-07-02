"""Auto-apply honest states: READY_TO_SUBMIT queue state + immediate dispatch on.

Revision ID: 0028_auto_apply_states
Revises: 0027_profile_search_prefs
Create Date: 2026-07-02

The auto-apply queue used to be a silent dead-end: jobs on boards without a
real submit adapter (LinkedIn / Indeed / Workday / manual / company pages)
sat in QUEUED_FOR_AUTO_APPLY forever, and with `auto_apply_enabled=False`
(the default) the cron skipped every row without a trace.

- `jobqueuestate` gains `READY_TO_SUBMIT` — "documents are prepared; this
  board needs YOU to submit" (with the reason recorded on
  `application.submission_artifacts.auto_apply`).
- `settings.auto_apply_immediate_dispatch` default flips to true (and
  existing rows are updated) so a right-swipe processes within seconds
  instead of waiting for the 5-minute cron. The cron remains the fallback.

Postgres-only for the enum (SQLite stores names as VARCHAR). Downgrade
restores the column default; enum values cannot be dropped in Postgres, so
READY_TO_SUBMIT stays (harmless).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028_auto_apply_states"
down_revision: str | None = "0027_profile_search_prefs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE jobqueuestate ADD VALUE IF NOT EXISTS 'READY_TO_SUBMIT'")

    op.alter_column(
        "settings",
        "auto_apply_immediate_dispatch",
        server_default=sa.text("true"),
        existing_type=sa.Boolean(),
        existing_nullable=False,
    )
    op.execute("UPDATE settings SET auto_apply_immediate_dispatch = true")


def downgrade() -> None:
    op.alter_column(
        "settings",
        "auto_apply_immediate_dispatch",
        server_default=sa.text("false"),
        existing_type=sa.Boolean(),
        existing_nullable=False,
    )
    # READY_TO_SUBMIT enum value intentionally left in place — Postgres has
    # no DROP VALUE; rows in that state degrade gracefully as SAVED-like.
