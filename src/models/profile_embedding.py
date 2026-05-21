"""ProfileEmbedding — one dense vector per user (plan 65, 0.3.0.03).

Mirrors `src/models/job_embedding.py` (plan 61 / 0.2.7.16) shape. Keyed
1:1 by `user_id`. Embedding text is `Profile.headline + summary + top-20
bullet texts ordered by Experience.order_index ASC, Bullet.order_index
ASC`.

Refresh policy (OQ-6, plan 65):
- On-edit via `services.profile_service.update_profile` /
  `services.profile_service.update_bullet` (synchronous, opt-in via
  `Settings.semantic_match_enabled`).
- Nightly idempotent batch via APScheduler
  `embeddings.embed_pending_profiles` at 02:30 UTC.

Dimensionality locked at 768d — same as JobEmbedding (decision D2 of plan
61). Provider swap mid-release survives via the `model` provenance column
+ nightly-batch refill (DROP+CREATE+refill pattern; decision D4).
"""

from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel

from ._common import utcnow
from .job_embedding import EMBEDDING_DIM  # shared 768d invariant


class ProfileEmbedding(SQLModel, table=True):
    __tablename__ = "profile_embedding"

    user_id: int = Field(primary_key=True, foreign_key="user.id")

    embedding: list[float] = Field(
        sa_column=Column(Vector(EMBEDDING_DIM), nullable=False),
    )

    # `<provider_id>/<model>@<effective-dim>` — same shape as JobEmbedding.
    model: str = Field(max_length=128)
    dim: int = Field(default=EMBEDDING_DIM)

    # SHA-1 of (headline || summary_short || summary_full || top-20 bullets).
    # Detects when Profile text changed; cron + on-edit skip when matched.
    content_hash: str = Field(max_length=64, index=True)

    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
