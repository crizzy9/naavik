"""Sibling table — one dense vector row per Job (1:1 keyed by `job_id`).

Plan 61 / `0.2.7.16` (2026-05-20). Materialized by the nightly APScheduler
batch (`scheduler.jobs.embed_pending_jobs` at 02:00 UTC); optionally synced
on `job_service.upsert_job` when `Settings.semantic_match_sync_on_upsert`
is True. Default: nightly only.

Dimensionality locked at 768d (decision D2) — covers OpenAI
text-embedding-3-small w/ Matryoshka truncation + Ollama nomic-embed-text
native. Dimensionality changes survive via DROP + CREATE TABLE +
nightly-batch refill (sibling-table strategy per decision D4).

Phase 6+ entity (graduates `docs/design/DATA_MODEL.md` § H pgvector stub).
"""

from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel

from ._common import utcnow

# Cross-provider stable column dim. Changing this is a `DROP TABLE
# job_embedding` + `CREATE TABLE` + nightly-batch refill operation.
EMBEDDING_DIM = 768


class JobEmbedding(SQLModel, table=True):
    __tablename__ = "job_embedding"

    job_id: int = Field(primary_key=True, foreign_key="job.id")
    user_id: int = Field(foreign_key="user.id", index=True)

    embedding: list[float] = Field(
        sa_column=Column(Vector(EMBEDDING_DIM), nullable=False),
    )

    # `<provider_id>/<model>@<effective-dim>` — e.g.
    # `openai/text-embedding-3-small@768` or `ollama/nomic-embed-text`.
    # Used by the nightly batch to skip rows that already match the
    # current provider+model combination.
    model: str = Field(max_length=128)
    dim: int = Field(default=EMBEDDING_DIM)

    # SHA-1 of (title || description); detects when Job text changed.
    content_hash: str = Field(max_length=64, index=True)

    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
