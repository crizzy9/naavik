"""Tracking v2 corrections substrate — plan 95 slice 95b.

Revision ID: 0042_tracking_v2_corrections
Revises: 0041_email_tracking_redesign
Create Date: 2026-07-07

Adds the correction-loop tables (plan 95 §§ 3.3–3.4):

- `classification_correction` — append-only labeled dataset of owner fixes
  (reclassify / unlink / merge / sender flags); the few-shot + eval substrate.
- `company_alias` — canonical-key alias map consulted by grouping/matching.
- `sender_rule` — per-sender treatment (agency / ignore / employer), checked
  before any LLM judgment is applied.

Plus the two `email_message` extraction columns slice 95c populates
(`extracted_sender_type`, `extracted_end_client`) — additive, nullable,
NULL until the classifier prompt gains the fields.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0042_tracking_v2_corrections"
down_revision = "0041_email_tracking_redesign"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "classification_correction",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "message_id",
            sa.Integer(),
            sa.ForeignKey("email_message.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("kind", sa.String(length=20), nullable=False, server_default="reclassify"),
        sa.Column("from_classification", sa.String(length=40), nullable=True),
        sa.Column("to_classification", sa.String(length=40), nullable=True),
        sa.Column("from_company", sa.String(length=160), nullable=True),
        sa.Column("to_company", sa.String(length=160), nullable=True),
        sa.Column("corrected_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('reclassify', 'unlink', 'merge_company', 'flag_sender')",
            name="ck_classification_correction_kind_vocab",
        ),
    )

    op.create_table(
        "company_alias",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("alias_key", sa.String(length=160), nullable=False),
        sa.Column("canonical_key", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "alias_key", name="uq_company_alias_user_alias"),
    )

    op.create_table(
        "sender_rule",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("matcher", sa.String(length=20), nullable=False),
        sa.Column("value", sa.String(length=254), nullable=False),
        sa.Column("treatment", sa.String(length=20), nullable=False),
        sa.Column("is_seed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_from_message_id",
            sa.Integer(),
            sa.ForeignKey("email_message.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "user_id", "matcher", "value", name="uq_sender_rule_user_matcher_value"
        ),
        sa.CheckConstraint(
            "matcher IN ('domain', 'company_key')",
            name="ck_sender_rule_matcher_vocab",
        ),
        sa.CheckConstraint(
            "treatment IN ('agency', 'ignore', 'employer')",
            name="ck_sender_rule_treatment_vocab",
        ),
    )

    op.add_column(
        "email_message",
        sa.Column("extracted_sender_type", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "email_message",
        sa.Column("extracted_end_client", sa.String(length=160), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("email_message", "extracted_end_client")
    op.drop_column("email_message", "extracted_sender_type")
    op.drop_table("sender_rule")
    op.drop_table("company_alias")
    op.drop_table("classification_correction")
