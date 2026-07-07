"""Correction-loop entities — plan 95 (tracking v2, § 3.3–3.4).

Corrections are data: every human override of the email pipeline persists
here and is reused (few-shot exemplars, regression evals, alias-aware
grouping, sender treatment) instead of being discarded.

- `ClassificationCorrection` — append-only labeled dataset of the owner's
  fixes (reclassify / unlink / merge). Consumed by the few-shot block in
  the classifier prompt and the `NAAVIK_EVAL_LLM=1` regression harness.
- `CompanyAlias` — maps a canonical company key variant to the key the
  owner said it belongs to ("bricoai" → "brico"). Consulted by grouping
  and matching forever after.
- `SenderRule` — per-sender ground truth (agency / ignore / employer),
  checked BEFORE the LLM result is applied: user rule > seed > LLM guess.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, UniqueConstraint
from sqlmodel import Field, SQLModel

from ._common import utcnow

# Correction kinds — what the human actually did.
CORRECTION_KINDS = ("reclassify", "unlink", "merge_company", "flag_sender")

# Sender-rule vocabularies (plan 95 § 3.3).
SENDER_RULE_MATCHERS = ("domain", "company_key")
SENDER_RULE_TREATMENTS = ("agency", "ignore", "employer")


class ClassificationCorrection(SQLModel, table=True):
    __tablename__ = "classification_correction"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('reclassify', 'unlink', 'merge_company', 'flag_sender')",
            name="ck_classification_correction_kind_vocab",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", ondelete="CASCADE", index=True)
    message_id: int = Field(foreign_key="email_message.id", ondelete="CASCADE", index=True)

    kind: str = Field(default="reclassify", max_length=20)
    from_classification: str | None = Field(default=None, max_length=40)
    to_classification: str | None = Field(default=None, max_length=40)
    from_company: str | None = Field(default=None, max_length=160)
    to_company: str | None = Field(default=None, max_length=160)

    corrected_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class CompanyAlias(SQLModel, table=True):
    __tablename__ = "company_alias"
    __table_args__ = (UniqueConstraint("user_id", "alias_key", name="uq_company_alias_user_alias"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", ondelete="CASCADE", index=True)

    # Both sides are canonical_company_key() outputs, not display names.
    alias_key: str = Field(max_length=160)
    canonical_key: str = Field(max_length=160)

    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class SenderRule(SQLModel, table=True):
    __tablename__ = "sender_rule"
    __table_args__ = (
        UniqueConstraint("user_id", "matcher", "value", name="uq_sender_rule_user_matcher_value"),
        CheckConstraint(
            "matcher IN ('domain', 'company_key')",
            name="ck_sender_rule_matcher_vocab",
        ),
        CheckConstraint(
            "treatment IN ('agency', 'ignore', 'employer')",
            name="ck_sender_rule_treatment_vocab",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", ondelete="CASCADE", index=True)

    matcher: str = Field(max_length=20)
    value: str = Field(max_length=254)
    treatment: str = Field(max_length=20)
    # True for the shipped staffing/outplacement seeds the user may delete.
    is_seed: bool = Field(default=False)

    created_from_message_id: int | None = Field(
        default=None,
        foreign_key="email_message.id",
        ondelete="SET NULL",
    )
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
