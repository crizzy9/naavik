"""Tier-3 fuzzy dedup — cross-source `(company, role)` match for Jobs.

Per docs/plans/34-0.2.0.09-job-dedup.md § D.2 + § D.4 (graduating to
docs/design/JOB_DEDUP.md). Tiers 1 (`(user_id, source, external_id)`
partial-unique) and 2 (`(user_id, url)` partial-unique) live structurally
in the schema (plan 27 migration 0005); tier 3 lives here.

Called inline from `job_service.upsert_job` BEFORE INSERT (and only when
tier-1 missed), so cross-board cross-posting (LinkedIn + Greenhouse + Lever
all surfacing the same Stripe role) lands as N rows where the second + Nth
carry `duplicate_of_id = first.id`. Discover UI filters them out by default.

Algorithm:

1. pg_trgm GIN-indexed `%` filter on `lower(Job.company)` narrows the N-row
   user pool to ~5-20 candidates whose company string is trigram-similar
   to the incoming.
2. For each candidate, weighted rapidfuzz score:
   `0.6 * token_set_ratio(company) + 0.4 * token_set_ratio(role)`.
3. Return the highest-scoring candidate >= 88.0 (0-100 scale); else None.
   Tie-break: oldest `found_at` wins (we shadow the new row to point at the
   pre-existing canonical row).
"""

from __future__ import annotations

from rapidfuzz import fuzz
from sqlalchemy import text
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import Job, JobSource

DEDUP_SCORE_THRESHOLD: float = 88.0
DEDUP_COMPANY_WEIGHT: float = 0.6
DEDUP_ROLE_WEIGHT: float = 0.4
DEDUP_CANDIDATE_LIMIT: int = 20


async def find_duplicate(
    session: AsyncSession,
    *,
    user_id: int,
    company: str,
    role: str,
    source: JobSource,
    excluded_job_id: int | None = None,
) -> Job | None:
    """Find a tier-3 fuzzy match for the (company, role) pair, or None.

    Same-source matches are skipped (tier-1's partial-unique handles those).
    Already-shadowed candidates (`duplicate_of_id IS NOT NULL`) are skipped
    to keep the dedup graph one-hop deep.

    Postgres-only candidate filter: uses the pg_trgm `%` operator to narrow
    via the `ix_job_company_trgm` GIN index. On sqlite (test substrate w/o
    pg_trgm), falls back to a case-insensitive substring filter on the same
    column — sufficient for the in-memory test harness; production runs
    Postgres.
    """
    norm_company = company.strip().lower()
    norm_role = role.strip().lower()
    if not norm_company or not norm_role:
        return None

    dialect = session.bind.dialect.name if session.bind is not None else "postgresql"

    base = select(Job).where(
        Job.user_id == user_id,
        Job.deleted_at.is_(None),
        Job.duplicate_of_id.is_(None),
        Job.source != source,
    )
    if excluded_job_id is not None:
        base = base.where(Job.id != excluded_job_id)

    if dialect == "postgresql":
        stmt = base.where(text("lower(job.company) % :norm_company")).params(
            norm_company=norm_company
        )
    else:
        stmt = base.where(text("lower(job.company) LIKE :like_company")).params(
            like_company=f"%{norm_company[:8]}%"
        )

    stmt = stmt.order_by(Job.found_at.asc()).limit(DEDUP_CANDIDATE_LIMIT)
    candidates = (await session.exec(stmt)).all()

    best: tuple[float, Job] | None = None
    for cand in candidates:
        cs = fuzz.token_set_ratio(norm_company, (cand.company or "").strip().lower())
        rs = fuzz.token_set_ratio(norm_role, (cand.role or "").strip().lower())
        score = DEDUP_COMPANY_WEIGHT * cs + DEDUP_ROLE_WEIGHT * rs
        if score >= DEDUP_SCORE_THRESHOLD and (best is None or score > best[0]):
            best = (score, cand)

    return best[1] if best else None


async def dedup_recent_jobs(
    session: AsyncSession,
    *,
    user_id: int,
    hours: int = 24,
) -> int:
    """Backfill `duplicate_of_id` on recent un-shadowed Jobs.

    Reserved for the 0.2.0.10 `jobs.dedup` cron + the one-off backfill an
    operator runs post-deploy when cross-source duplicates already exist in
    their DB (per plan 34 § D.6 round-trip note). Returns the count of new
    links established.
    """
    from datetime import UTC, datetime, timedelta

    threshold = datetime.now(UTC) - timedelta(hours=hours)
    stmt = (
        select(Job)
        .where(
            Job.user_id == user_id,
            Job.deleted_at.is_(None),
            Job.duplicate_of_id.is_(None),
            Job.found_at >= threshold,
        )
        .order_by(Job.found_at.asc())
    )
    rows = (await session.exec(stmt)).all()

    linked = 0
    for row in rows:
        match = await find_duplicate(
            session,
            user_id=user_id,
            company=row.company,
            role=row.role,
            source=row.source,
            excluded_job_id=row.id,
        )
        if match is not None and match.id != row.id:
            row.duplicate_of_id = match.id
            session.add(row)
            linked += 1

    if linked:
        await session.flush()
    return linked
