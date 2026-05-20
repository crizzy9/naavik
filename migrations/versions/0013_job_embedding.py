"""JobEmbedding + Settings semantic-match columns — plan 61 (0.2.7.16).

Revision ID: 0013_job_embedding
Revises: 0012_profile_answer
Create Date: 2026-05-20

Per `docs/plans/61-0.2.7.14-0.2.7.16-profile-answer-job-embedding.md` § B.2 + B.3.

Postgres-only operations (pgvector extension + HNSW index + `vector(N)`
column type). On sqlite (tests), the embedding column degrades to TEXT and
the HNSW index becomes a no-op — covered by `tests/test_alembic_0013.py`'s
columns-present assertion + sqlite-safe DDL guard.

The `CREATE EXTENSION vector` is idempotent (`IF NOT EXISTS`). The HNSW
index ships with the documented sub-100K-row defaults (`m=16,
ef_construction=200`) per decision D5 — first build on an empty table is
cheap; subsequent online inserts go to HNSW's online-insert path.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_job_embedding"
down_revision: str | None = "0012_profile_answer"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_EMBEDDING_DIM = 768


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "job_embedding",
        sa.Column(
            "job_id",
            sa.Integer(),
            sa.ForeignKey("job.id"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("user.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "embedding",
            # pgvector's VECTOR(N) on Postgres; TEXT on sqlite (tests only).
            sa.Text() if not is_postgres else sa.Text().with_variant(sa.Text(), "sqlite"),
            nullable=False,
        ),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("dim", sa.Integer(), nullable=False, server_default=str(_EMBEDDING_DIM)),
        sa.Column("content_hash", sa.String(length=64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    if is_postgres:
        # Rewrite the embedding column to native VECTOR(N). Using ALTER TABLE
        # ... TYPE rather than dropping the placeholder TEXT column avoids
        # the column-rename dance.
        op.execute(
            f"ALTER TABLE job_embedding ALTER COLUMN embedding TYPE vector({_EMBEDDING_DIM}) USING NULL"
        )
        op.execute(
            "CREATE INDEX ix_job_embedding_embedding_cosine "
            "ON job_embedding USING hnsw (embedding vector_cosine_ops) "
            "WITH (m = 16, ef_construction = 200)"
        )

    op.add_column(
        "settings",
        sa.Column(
            "semantic_match_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "settings",
        sa.Column("embedding_provider", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "settings",
        sa.Column(
            "semantic_match_threshold",
            sa.Float(),
            nullable=False,
            server_default="0.65",
        ),
    )
    op.add_column(
        "settings",
        sa.Column(
            "semantic_match_sync_on_upsert",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    op.drop_column("settings", "semantic_match_sync_on_upsert")
    op.drop_column("settings", "semantic_match_threshold")
    op.drop_column("settings", "embedding_provider")
    op.drop_column("settings", "semantic_match_enabled")

    if is_postgres:
        op.execute("DROP INDEX IF EXISTS ix_job_embedding_embedding_cosine")

    op.drop_table("job_embedding")
    # The vector extension stays — 0001_initial already enables it, and
    # other future tables may rely on it (decision D4 ack).
