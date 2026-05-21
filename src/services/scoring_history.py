"""Per-role-family score history aggregation — plan 73 (0.3.2.03).

Reads `Job.match_breakdown` rows scored within the last 30 days, classifies
`Job.role` to a role-family via heuristic substring match, groups by family
and day, computes daily means, and writes the resulting blob to
`Profile.score_history`. The cron `score.aggregate_daily` (APScheduler,
daily 03:30 UTC) is the sole writer.

Blob shape (per docs/design/MOCKUP_HANDOFF-0.3.2.md § Surface 3):

    {
      "last_aggregated_at": "<iso ts UTC>",
      "families": [
        {
          "family": str,            # one of the 9 Tag values or "other"
          "scored_count_30d": int,
          "score_current": float,   # most recent daily mean
          "score_delta_30d": float, # current - first non-null
          "daily_means": [float | None, ...]  # length == window_days
        },
        ...
      ]
    }

Q73.3 lock: heuristic substring classifier — no LLM cost per snapshot.
LLM-judge upgrade is a future 0.8.0.NN follow-up.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import Job, Profile

# Tag enum 9-value vocabulary + "other" fallback. Order is the canonical
# render order; families that don't surface get filtered before write.
# Iteration order doubles as classifier priority — narrowest patterns
# (genai before ai-ml; leadership before backend's generic "software engineer")
# sit higher in the dict.
_ROLE_FAMILY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "genai": (
        "genai",
        "gen-ai",
        "gen ai",
        "generative ai",
        "llm",
        "language model",
        "prompt engineer",
        "rag ",
        "agent ",
    ),
    "ai-ml": (
        "ml engineer",
        "ml ",
        "machine learning",
        "ai engineer",
        "ai ",
        "ai/ml",
        "data scientist",
        "data science",
        "applied scientist",
        "research scientist",
        "research engineer",
    ),
    "frontend": (
        "frontend",
        "front-end",
        "front end",
        "ui engineer",
        "ux engineer",
        "web engineer",
        "react",
        "typescript engineer",
    ),
    "data-eng": (
        "data engineer",
        "data engineering",
        "analytics engineer",
        "etl",
        "warehouse",
        "pipeline engineer",
    ),
    "devops": (
        "devops",
        "sre",
        "site reliability",
        "infrastructure engineer",
        "infra engineer",
        "cloud engineer",
        "release engineer",
    ),
    "platform": (
        "platform",
        "developer platform",
        "internal tools",
        "infra ",
    ),
    "leadership": (
        "engineering manager",
        "staff engineer",
        "principal engineer",
        "director of engineering",
        "head of engineering",
        "tech lead",
        "lead engineer",
        "vp engineering",
        "vp of engineering",
    ),
    "product": (
        "product engineer",
        "product manager",
        "founding engineer",
        "founding product",
    ),
    "backend": (
        "backend",
        "back-end",
        "back end",
        "server engineer",
        "api engineer",
        "distributed systems",
        "software engineer",  # generic SWE → backend by convention
    ),
}

_FAMILY_ORDER: tuple[str, ...] = (
    "ai-ml",
    "backend",
    "frontend",
    "devops",
    "data-eng",
    "genai",
    "leadership",
    "platform",
    "product",
    "other",
)


def classify_role_family(role: str | None) -> str:
    """Return the role-family bucket for `role` via substring match.

    Case-insensitive. Family order in `_ROLE_FAMILY_KEYWORDS` defines
    priority — generic terms like "software engineer" sit last so more
    specific patterns (e.g. "ml engineer") win.
    """
    if not role:
        return "other"
    needle = role.lower()
    for family, keywords in _ROLE_FAMILY_KEYWORDS.items():
        for kw in keywords:
            if kw in needle:
                return family
    return "other"


def _midnight_utc(d: datetime) -> datetime:
    return d.replace(hour=0, minute=0, second=0, microsecond=0)


def _parse_scored_at(raw: Any) -> datetime | None:
    """Tolerant parse of `match_breakdown.scored_at` (string OR datetime)."""
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=UTC)
    if isinstance(raw, str):
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    return None


def _coerce_score(raw: Any) -> float | None:
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        try:
            return float(raw)
        except ValueError:
            return None
    return None


async def aggregate_score_history(
    session: AsyncSession,
    user_id: int,
    *,
    window_days: int = 30,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Compute the per-role-family score-history blob for `user_id`.

    Window is `window_days` ending at the start of `now`'s UTC day. Jobs are
    filtered by `Job.user_id == user_id`, `Job.deleted_at IS NULL`, and any
    `match_breakdown.scored_at` ≥ window start. Empty families are dropped.

    Missing-day handling: a family's `daily_means[i]` is `None` when no
    job was scored that day; the template carries-forward when rendering.
    """
    now = (now or datetime.now(UTC)).astimezone(UTC)
    today_start = _midnight_utc(now)
    window_start = today_start - timedelta(days=window_days - 1)

    stmt = select(Job).where(
        Job.user_id == user_id,
        Job.deleted_at.is_(None),
    )
    rows = (await session.exec(stmt)).all()

    # family -> day_index -> list[float]
    buckets: dict[str, list[list[float]]] = {}

    for job in rows:
        breakdown = job.match_breakdown or {}
        scored_at = _parse_scored_at(breakdown.get("scored_at"))
        if scored_at is None or scored_at < window_start or scored_at > now:
            continue
        score = _coerce_score(breakdown.get("score"))
        if score is None:
            continue
        day_idx = (_midnight_utc(scored_at) - window_start).days
        if day_idx < 0 or day_idx >= window_days:
            continue
        family = classify_role_family(job.role)
        if family not in buckets:
            buckets[family] = [[] for _ in range(window_days)]
        buckets[family][day_idx].append(score)

    families: list[dict[str, Any]] = []
    for family in _FAMILY_ORDER:
        days = buckets.get(family)
        if days is None:
            continue
        scored_count = sum(len(b) for b in days)
        if scored_count == 0:
            continue
        daily_means: list[float | None] = []
        for bucket in days:
            daily_means.append(sum(bucket) / len(bucket) if bucket else None)
        non_null = [m for m in daily_means if m is not None]
        score_current = non_null[-1] if non_null else 0.0
        first_non_null = non_null[0] if non_null else 0.0
        score_delta = score_current - first_non_null
        families.append(
            {
                "family": family,
                "scored_count_30d": scored_count,
                "score_current": round(score_current, 4),
                "score_delta_30d": round(score_delta, 4),
                "daily_means": [round(m, 4) if m is not None else None for m in daily_means],
            }
        )

    return {
        "last_aggregated_at": now.isoformat(),
        "families": families,
    }


async def update_profile_score_history(
    session: AsyncSession,
    user_id: int,
    *,
    window_days: int = 30,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Aggregate then write the blob to `Profile.score_history`.

    Returns the blob on success, None when the user has no Profile row.
    Caller commits.
    """
    profile = (
        await session.exec(
            select(Profile).where(
                Profile.user_id == user_id,
                Profile.deleted_at.is_(None),
            )
        )
    ).one_or_none()
    if profile is None:
        return None
    blob = await aggregate_score_history(session, user_id, window_days=window_days, now=now)
    profile.score_history = blob
    profile.updated_at = datetime.now(UTC)
    session.add(profile)
    await session.flush()
    return blob


__all__ = [
    "aggregate_score_history",
    "classify_role_family",
    "update_profile_score_history",
]
