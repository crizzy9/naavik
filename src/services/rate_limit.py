"""Per-user in-memory rate limiter — plan 75 / 0.3.3.02 + 0.3.3.06.

Mirrors the IP-keyed brute-force guard pattern at
`services/auth.py:351-380` but keys by `user_id` for authenticated routes.
Single-instance MVP; cloud-tier multi-instance migration deferred to 0.4.x
(needs Redis or row-lock equivalent).

Two FastAPI deps shipped with this module:

- `check_rescore_rate_limit` — applied to `POST /api/v1/jobs/{id}/rescore`
  (10/min, 60/hr per user).
- `check_generate_bundle_rate_limit` — applied to
  `POST /api/v1/applications/{id}/generate-bundle` (10/hr per user).

`_user=None` (fake-session bypass per plan 23) is skipped — mirrors
`auth.py:354-380`'s IP-only gating where the fake substrate has no
real user identity to limit.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, status

from models import User
from services.auth import require_authed_session


@dataclass(slots=True)
class RateLimit:
    """Sliding-window rate limiter.

    `window` is the time horizon (e.g. 1 min, 1 hr). `threshold` is the
    maximum events permitted per `user_id` within that window. State is
    purely in-memory; restart resets all buckets.
    """

    window: timedelta
    threshold: int
    buckets: dict[int, deque[datetime]] = field(default_factory=dict)

    def record(self, user_id: int) -> None:
        bucket = self.buckets.setdefault(user_id, deque())
        now = datetime.now(UTC)
        cutoff = now - self.window
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        bucket.append(now)

    def is_limited(self, user_id: int) -> bool:
        bucket = self.buckets.get(user_id)
        if not bucket:
            return False
        cutoff = datetime.now(UTC) - self.window
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        return len(bucket) >= self.threshold

    def reset(self, user_id: int | None = None) -> None:
        """Test helper — clear all buckets or one user's bucket."""
        if user_id is None:
            self.buckets.clear()
        else:
            self.buckets.pop(user_id, None)


# ── Module-level singletons ──────────────────────────────────────────────

# Plan 75 / 0.3.3.02 — manual rescore. DB CPU + orchestrator burn happens
# before the per-call cost-cap probe; rate limit is the proper defense
# layer for the path below the LLM gate.
RESCORE_LIMIT_MIN = RateLimit(window=timedelta(minutes=1), threshold=10)
RESCORE_LIMIT_HR = RateLimit(window=timedelta(hours=1), threshold=60)

# Plan 75 / 0.3.3.06 — generate-bundle. One bundle is ~$0.06-0.12 (FREE
# tier) or ~$0.40-1.20 (PREMIUM); cost-cap probe protects spend but a
# runaway client can still exhaust daily cap quickly.
GENERATE_BUNDLE_LIMIT_HR = RateLimit(window=timedelta(hours=1), threshold=10)


def _enforce(
    limiter: RateLimit,
    user_id: int,
    *,
    name: str,
) -> None:
    if limiter.is_limited(user_id):
        retry_after = int(limiter.window.total_seconds())
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"rate limited: {name}",
            headers={"Retry-After": str(retry_after)},
        )
    limiter.record(user_id)


async def check_rescore_rate_limit(
    _user: User | None = Depends(require_authed_session),
) -> None:
    """Plan 75 / 0.3.3.02 — 10/min, 60/hr per user for rescore.

    Skips fake-session callers (`_user is None`) — those go through the
    transitional auth-stub path and don't have a stable user identity.
    """
    if _user is None:
        return
    _enforce(RESCORE_LIMIT_MIN, _user.id, name="rescore/min")
    _enforce(RESCORE_LIMIT_HR, _user.id, name="rescore/hr")


async def check_generate_bundle_rate_limit(
    _user: User | None = Depends(require_authed_session),
) -> None:
    """Plan 75 / 0.3.3.06 — 10/hr per user for bundle generation."""
    if _user is None:
        return
    _enforce(GENERATE_BUNDLE_LIMIT_HR, _user.id, name="generate-bundle/hr")


def reset_all() -> None:
    """Test helper — clear every limiter."""
    RESCORE_LIMIT_MIN.reset()
    RESCORE_LIMIT_HR.reset()
    GENERATE_BUNDLE_LIMIT_HR.reset()
