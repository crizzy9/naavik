"""Settings.auto_apply_adapter_confidence_threshold (plan 63 / 0.2.7.10 § D.5).

Revision ID: 0016_ats_adapter_confidence_threshold
Revises: 0015_tenant_signing_key_active_uniq
Create Date: 2026-05-20

Per docs/plans/63-0.2.7.10-ats-adapters.md § D.5 + § G. Pairs with the new
`SubmissionResult.confidence: float | None` field (HTTP adapters always emit
1.0; Generic adapter emits LLM-form-fill confidence). Below this threshold →
caller reverts state to DRAFT and surfaces in the manual-review queue.

`server_default='0.7'` matches the plan's locked default; preserves current
behavior on upgrade (HTTP adapters emit `confidence=1.0` so they pass any
threshold in [0, 1]).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_ats_adapter_confidence_threshold"
down_revision: str | None = "0015_tenant_signing_key_active_uniq"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "settings",
        sa.Column(
            "auto_apply_adapter_confidence_threshold",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.7"),
        ),
    )


def downgrade() -> None:
    op.drop_column("settings", "auto_apply_adapter_confidence_threshold")
