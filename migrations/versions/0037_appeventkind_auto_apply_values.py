"""AppEventKind AUTO_APPLY_* enum values — fix upgrade-path crash.

Revision ID: 0037_appeventkind_auto_apply_values
Revises: 0036_section_selection_override
Create Date: 2026-07-04

Plan 91 Phase 1.5. `AppEventKind.AUTO_APPLY_DRY_RUN / AUTO_APPLY_DRAINED /
AUTO_APPLY_VISA_BLOCKED / AUTO_APPLY_QUEUED` (plans 78 / 79) were added to the
Python enum but never got an `ALTER TYPE appeventkind ADD VALUE` migration.
Fresh installs are unaffected (0001 rebuilds the enum from live members), but a
DB whose 0001 ran before plan 78 raises `invalid input value for enum
appeventkind: "AUTO_APPLY_DRY_RUN"` the first time auto-apply emits one of
these events. This backfills the four labels.

Labels are the Python member NAMES — SQLAlchemy binds names with
`native_enum=True` (see 0024 / 0026_enum_label_names). `ADD VALUE IF NOT
EXISTS` makes it idempotent. Postgres cannot DROP enum values before v16, so
downgrade is a documented no-op (matches 0022 / 0028).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0037_appeventkind_auto_apply_values"
down_revision: str | None = "0036_section_selection_override"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_VALUES = (
    "AUTO_APPLY_DRY_RUN",
    "AUTO_APPLY_DRAINED",
    "AUTO_APPLY_VISA_BLOCKED",
    "AUTO_APPLY_QUEUED",
)


def upgrade() -> None:
    # Enum values only exist on Postgres; sqlite/other dialects are a no-op.
    if op.get_bind().dialect.name != "postgresql":
        return
    # ADD VALUE cannot run inside a transaction block.
    with op.get_context().autocommit_block():
        for value in _NEW_VALUES:
            op.execute(f"ALTER TYPE appeventkind ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    # Postgres cannot remove enum values before v16; no-op (see 0022 / 0028).
    pass
