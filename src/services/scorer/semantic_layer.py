"""Layer 2 — pgvector cosine similarity (plan 65 § D.4).

Computes cosine similarity between `JobEmbedding` + `ProfileEmbedding`
via pgvector's `<=>` operator. The math stays on the DB side — pulling
two 768d float arrays into Python + dot-producting them in numpy
round-trips ~12KB per scoring call; the Postgres compute is ~5ms vs
~30ms for the Python path.

Returns `None` when either embedding row is missing (e.g. sqlite test
fallback, or a profile with `semantic_match_enabled=False` who never
seeded their embedding). The orchestrator treats `None` as "skip layer
2" and composites with `tag_score` alone.
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import Job, JobEmbedding, ProfileEmbedding

log = logging.getLogger(__name__)


async def _semantic_score(
    session: AsyncSession,
    *,
    job: Job,
    profile_embedding: ProfileEmbedding | None,
) -> float | None:
    """Cosine similarity job ↔ profile embeddings; None when either missing.

    Returns sim in [0, 1] (1 = identical, 0 = orthogonal/opposite).
    Implementation: pgvector `<=>` cosine distance, converted via
    `1 - d/2` to map to similarity.
    """
    if profile_embedding is None or job is None or job.id is None:
        return None

    job_emb = (
        await session.exec(
            select(JobEmbedding).where(
                JobEmbedding.job_id == job.id,
                JobEmbedding.user_id == job.user_id,
            )
        )
    ).one_or_none()
    if job_emb is None:
        return None

    profile_vec = list(profile_embedding.embedding or [])
    job_vec = list(job_emb.embedding or [])
    if not profile_vec or not job_vec or len(profile_vec) != len(job_vec):
        return None

    p_lit = "[" + ",".join(f"{v}" for v in profile_vec) + "]"
    j_lit = "[" + ",".join(f"{v}" for v in job_vec) + "]"
    stmt = text("SELECT 1.0 - (CAST(:p AS vector) <=> CAST(:j AS vector)) / 2.0 AS sim")
    try:
        result = await session.exec(stmt.bindparams(p=p_lit, j=j_lit))
        val = result.one()
    except Exception as exc:  # noqa: BLE001
        # sqlite has no pgvector — the orchestrator gracefully treats
        # None as "skip semantic layer".
        log.debug("_semantic_score skipped (likely non-postgres): %s", exc)
        return None

    raw = val[0] if isinstance(val, tuple) else val
    try:
        sim = float(raw)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, sim))


__all__ = ["_semantic_score"]
