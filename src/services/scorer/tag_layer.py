"""Layer 1b — weighted tag overlap (plan 65 § T3, § T4).

Asymmetric formula — measures profile coverage of the job's tags. A
profile with 7 tags scoring a job with 3 tags gets full credit if all 3
job tags are covered; symmetric Jaccard would penalize that.

Pure-Python + deterministic — no LLM call. Per-tag weight resolution
flows through `weights.py:resolve_weights` for operator tunability.
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import Bullet, Experience, Profile
from models.enums import Tag


async def aggregated_profile_tags(session: AsyncSession, *, profile: Profile) -> frozenset[str]:
    """Union of Bullet.tags across the profile's experiences.

    Filters soft-deleted bullets + experiences. Returns a frozenset of
    Tag enum-value strings (e.g. {"ai-ml", "platform", "leadership"}).
    Unknown tag values that may have leaked into older rows are dropped.
    """
    if profile is None or profile.id is None:
        return frozenset()
    stmt = (
        select(Bullet.tags)
        .join(Experience, Bullet.experience_id == Experience.id)
        .where(
            Experience.profile_id == profile.id,
            Bullet.deleted_at.is_(None),
            Experience.deleted_at.is_(None),
        )
    )
    rows = (await session.exec(stmt)).all()
    allowed = {t.value for t in Tag}
    out: set[str] = set()
    for row in rows:
        if not row:
            continue
        for tag in row:
            if tag in allowed:
                out.add(tag)
    return frozenset(out)


def _tag_overlap_score(
    job_tags: Iterable[str] | None,
    profile_tags: frozenset[str],
    weights: dict[str, float],
) -> float:
    """Weighted overlap — asymmetric, profile-coverage of job's tags.

    Formula:
        numerator   = sum(weights[t] for t in J ∩ P)
        denominator = sum(weights[t] for t in J)
        score       = numerator / denominator if denominator > 0 else 0.0

    Returns a float in [0, 1].
    """
    job_set = frozenset(job_tags or ())
    if not job_set:
        return 0.0
    numerator = sum(weights.get(t, 1.0) for t in (job_set & profile_tags))
    denominator = sum(weights.get(t, 1.0) for t in job_set)
    if denominator <= 0:
        return 0.0
    return min(1.0, max(0.0, numerator / denominator))


__all__ = ["_tag_overlap_score", "aggregated_profile_tags"]
