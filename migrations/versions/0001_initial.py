"""initial — every entity per docs/design/DATA_MODEL.md § C.

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-02

Single migration covering the full Phase 1 schema:
- pgvector extension (cheap insurance for Phase 6 JobEmbedding)
- 20 tables (19 entities + Settings singleton)
- Every Postgres ENUM type backing the StrEnum vocabulary
- Indexes per DATA_MODEL.md § G (incl. GIN on tag arrays + partial uniques)
- CHECK constraints per DATA_MODEL.md § E (incl. corrected 2026-05-01
  Application.applied_at form covering DRAFT, post-submission, and
  discarded-DRAFT cases)

Implementation: drives DDL straight from `SQLModel.metadata` so future
schema changes can use Alembic autogenerate against the live DB.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlmodel import SQLModel

# Importing the package registers every entity in SQLModel.metadata.
import models  # noqa: F401

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    # pgvector enables future Phase 6 JobEmbedding without a re-run.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    SQLModel.metadata.create_all(bind, checkfirst=False)


def downgrade() -> None:
    bind = op.get_bind()
    SQLModel.metadata.drop_all(bind, checkfirst=False)
    op.execute("DROP EXTENSION IF EXISTS vector")
