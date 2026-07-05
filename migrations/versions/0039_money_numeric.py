"""Money columns float → NUMERIC(10,4).

Revision ID: 0039_money_numeric
Revises: 0038_index_hygiene
Create Date: 2026-07-05

Plan 91 Phase 7.2. `api_usage.cost_usd` and `generated_document.cost_usd`
were `double precision` — binary floats accumulate representation error on
money, and the daily-cap comparison reads a SUM over thousands of rows.
NUMERIC(10,4) stores exact 4-decimal USD (max $999,999.9999 per row). The
models read the column with `asdecimal=False` so Python callers keep
receiving floats — no runtime type churn.

Postgres-only: the sqlite test substrate builds from model metadata
directly (NUMERIC affinity there is fine), and sqlite ALTER TYPE needs a
table rebuild for zero benefit.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0039_money_numeric"
down_revision: str | None = "0038_index_hygiene"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.alter_column(
        "api_usage",
        "cost_usd",
        type_=sa.Numeric(10, 4),
        existing_type=sa.Float(),
        existing_nullable=False,
    )
    op.alter_column(
        "generated_document",
        "cost_usd",
        type_=sa.Numeric(10, 4),
        existing_type=sa.Float(),
        existing_nullable=True,
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.alter_column(
        "generated_document",
        "cost_usd",
        type_=sa.Float(),
        existing_type=sa.Numeric(10, 4),
        existing_nullable=True,
    )
    op.alter_column(
        "api_usage",
        "cost_usd",
        type_=sa.Float(),
        existing_type=sa.Numeric(10, 4),
        existing_nullable=False,
    )
