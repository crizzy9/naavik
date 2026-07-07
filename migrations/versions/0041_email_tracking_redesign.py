"""Email tracking redesign — extracted entities + poisoned-classification reset.

Revision ID: 0041_email_tracking_redesign
Revises: 0040_closed_vocab_checks
Create Date: 2026-07-06

2026-07 tracking redesign:

1. `email_message` gains `extracted_company` / `extracted_role` /
   `extracted_stage` (classifier entity extraction — powers company→
   application mapping and the detected-processes panel) and
   `process_dismissed_at` (per-group "not mine" dismissal).

2. Data repair — every pre-redesign classification is untrustworthy: the
   classifier read `StructuredResult.value` (a dict) with `getattr`, so the
   `"other"` default won on EVERY message regardless of what the LLM
   returned. Reset OTHER rows (only rows with no user-facing suggestion
   state) to NULL so the classifier cron re-runs them through the fixed
   pipeline. Receipt-inference markers reset with them so unlinked messages
   get a second pass.

3. Data repair — subjects/sender names were stored as raw RFC 2047
   encoded-words with folded whitespace; decode in place so old rows render
   (and re-classify) cleanly.
"""

from __future__ import annotations

import email.header

import sqlalchemy as sa
from alembic import op

revision = "0041_email_tracking_redesign"
down_revision = "0040_closed_vocab_checks"
branch_labels = None
depends_on = None


def _decode_header(raw: str | None) -> str | None:
    if not raw:
        return raw
    try:
        decoded = str(email.header.make_header(email.header.decode_header(raw)))
    except Exception:  # noqa: BLE001 — malformed encoded-word: keep the raw text
        decoded = raw
    return " ".join(decoded.split())


def upgrade() -> None:
    op.add_column(
        "email_message",
        sa.Column("extracted_company", sa.String(length=160), nullable=True),
    )
    op.add_column(
        "email_message",
        sa.Column("extracted_role", sa.String(length=160), nullable=True),
    )
    op.add_column(
        "email_message",
        sa.Column("extracted_stage", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "email_message",
        sa.Column("process_dismissed_at", sa.DateTime(timezone=True), nullable=True),
    )

    bind = op.get_bind()

    # 3 — decode RFC 2047 subjects / sender names in place.
    for table, columns in (
        ("email_message", ("subject", "sender_name")),
        ("email_thread", ("subject",)),
    ):
        rows = bind.execute(
            sa.text(f"SELECT id, {', '.join(columns)} FROM {table}")  # noqa: S608
        ).fetchall()
        for row in rows:
            updates = {}
            for idx, col in enumerate(columns, start=1):
                raw = row[idx]
                decoded = _decode_header(raw)
                if decoded != raw:
                    updates[col] = decoded
            if updates:
                assignments = ", ".join(f"{col} = :{col}" for col in updates)
                bind.execute(
                    sa.text(f"UPDATE {table} SET {assignments} WHERE id = :id"),  # noqa: S608
                    {**updates, "id": row[0]},
                )

    # 2 — reset poisoned classifications for a clean re-run. Guard on
    # suggestion state so anything a user already acted on is left alone
    # (OTHER rows never got suggestions, so in practice this is all of them).
    bind.execute(
        sa.text(
            """
            UPDATE email_message
               SET classification = NULL,
                   classification_at = NULL,
                   classification_model = NULL,
                   urgency = NULL,
                   unclassified_reason = NULL,
                   inference_processed_at = CASE
                       WHEN application_id IS NULL THEN NULL
                       ELSE inference_processed_at
                   END
             WHERE classification = 'OTHER'
               AND suggested_status IS NULL
               AND suggestion_applied_at IS NULL
               AND suggestion_dismissed_at IS NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_column("email_message", "process_dismissed_at")
    op.drop_column("email_message", "extracted_stage")
    op.drop_column("email_message", "extracted_role")
    op.drop_column("email_message", "extracted_company")
    # The classification reset and header decode are one-way data repairs.
