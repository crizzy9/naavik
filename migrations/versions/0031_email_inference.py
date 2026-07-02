"""Email-inferred applications — JobSource.EMAIL + inference marker.

Revision ID: 0031_email_inference
Revises: 0030_calendar_events
Create Date: 2026-07-02

Item 5: application-confirmation receipts in the inbox become proposed
Applications (+ library Jobs with source=email when nothing matches).
`email_message.inference_processed_at` marks receipts already examined.
Postgres enum values cannot be dropped — downgrade leaves EMAIL in place
(harmless), matching the 0028 READY_TO_SUBMIT precedent.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031_email_inference"
down_revision: str | None = "0030_calendar_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE jobsource ADD VALUE IF NOT EXISTS 'EMAIL'")
    op.add_column(
        "email_message",
        sa.Column("inference_processed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("email_message", "inference_processed_at")
