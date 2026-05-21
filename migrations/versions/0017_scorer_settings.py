"""ProfileEmbedding + Settings.score_per_dim_weights — plan 65 (0.3.0).

Revision ID: 0017_scorer_settings
Revises: 0016_ats_adapter_confidence_threshold
Create Date: 2026-05-21

Per `docs/plans/65-0.3.0-scoring-substrate.md` § D.3 + § D.7. Mirrors
alembic 0013's split between dialect-portable column setup + Postgres-only
vector(N) rewrite + HNSW index.

Postgres-only operations (pgvector + HNSW index + vector(N) column type).
On sqlite (tests), the embedding column degrades to TEXT and the HNSW
index becomes a no-op — covered by `tests/test_alembic_0017.py`'s
columns-present assertion.

The `CREATE EXTENSION vector` is idempotent (0001_initial + 0013 already
created it).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0017_scorer_settings"
down_revision: str | None = "0016_ats_adapter_confidence_threshold"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_EMBEDDING_DIM = 768


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "profile_embedding",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("user.id"),
            primary_key=True,
        ),
        sa.Column(
            "embedding",
            sa.Text(),
            nullable=False,
        ),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("dim", sa.Integer(), nullable=False, server_default=str(_EMBEDDING_DIM)),
        sa.Column("content_hash", sa.String(length=64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    if is_postgres:
        op.execute(
            f"ALTER TABLE profile_embedding ALTER COLUMN embedding "
            f"TYPE vector({_EMBEDDING_DIM}) USING NULL"
        )
        op.execute(
            "CREATE INDEX ix_profile_embedding_embedding_cosine "
            "ON profile_embedding USING hnsw (embedding vector_cosine_ops) "
            "WITH (m = 16, ef_construction = 200)"
        )

    # Settings.score_per_dim_weights — JSONB on Postgres, JSON on sqlite.
    score_weights_col_type = JSONB() if is_postgres else sa.JSON()
    op.add_column(
        "settings",
        sa.Column(
            "score_per_dim_weights",
            score_weights_col_type,
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    op.drop_column("settings", "score_per_dim_weights")

    if is_postgres:
        op.execute("DROP INDEX IF EXISTS ix_profile_embedding_embedding_cosine")

    op.drop_table("profile_embedding")
    # The vector extension stays — 0001_initial + 0013 created it; other
    # consumers (job_embedding) still need it.
