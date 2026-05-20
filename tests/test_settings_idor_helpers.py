"""Plan 57 / 0.2.7.23 — sibling IDOR helpers in `src/ui/routes/settings.py`.

Filed via PR #156 hacker observation. Plan 56 / 0.2.7.02 fixed
`_build_sources_view`'s hardcoded `user_id=1`; the same shape persisted in
three sibling view fns:

  * `_recent_scrape_runs_view` → `job_service.list_recent_scrape_runs`
  * `_submission_failures_view` → `application_service.aggregate_submission_failures`
  * `_llm_cost_cap_view` → `llm_tracker.today_cost_usd`

Each must now thread the route-supplied `user_id` (resolved via
`_effective_user_id(user)` at the boundary). Not exploitable in single-user
Phase 1, becomes cross-user info-disclosure on multi-user.

Test slate (2 per helper):
  1. Spy that `user_id=N` reaches the service call (threading).
  2. Cross-user filter: spy distinguishes user-1 vs user-42 calls and
     proves each helper passes the correct id.

The cross-user "filter" tests don't require NAAVIK_LIVE_DB — the service
layer is monkeypatched, so the assertion is purely on what user_id reaches
the (mocked) service. Real cross-user filtering is tested at the
service-layer in `test_job_service.py` / `test_application_service.py` /
`test_llm_tracker.py`.
"""

from __future__ import annotations

import asyncio
import os

os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")
os.environ.setdefault("NAAVIK_DEBUG", "1")
os.environ["NAAVIK_PERSISTENCE"] = "memory"


class _NoopSession:
    """Minimum surface for `Depends(get_session)` — service ops are
    monkeypatched, so this never runs SQL.
    """

    async def commit(self):  # pragma: no cover
        return None

    async def rollback(self):  # pragma: no cover
        return None

    async def close(self):  # pragma: no cover
        return None


# ── _recent_scrape_runs_view ─────────────────────────────────────────────


def test_recent_scrape_runs_view_threads_user_id(monkeypatch):
    """`_recent_scrape_runs_view(session, user_id=N)` passes N to job_service."""
    from services import job_service
    from ui.routes import settings as settings_routes

    captured: dict[str, int] = {}

    async def _spy(session, *, user_id, limit=50):
        captured["user_id"] = user_id
        return []

    monkeypatch.setattr(job_service, "list_recent_scrape_runs", _spy)

    asyncio.run(settings_routes._recent_scrape_runs_view(_NoopSession(), user_id=42))

    assert captured == {"user_id": 42}


def test_recent_scrape_runs_view_distinct_users_get_distinct_calls(monkeypatch):
    """Cross-user: user-1 + user-42 each thread their own id through."""
    from services import job_service
    from ui.routes import settings as settings_routes

    seen: list[int] = []

    async def _spy(session, *, user_id, limit=50):
        seen.append(user_id)
        return []

    monkeypatch.setattr(job_service, "list_recent_scrape_runs", _spy)

    asyncio.run(settings_routes._recent_scrape_runs_view(_NoopSession(), user_id=1))
    asyncio.run(settings_routes._recent_scrape_runs_view(_NoopSession(), user_id=42))

    assert seen == [1, 42]


# ── _submission_failures_view ────────────────────────────────────────────


def test_submission_failures_view_threads_user_id(monkeypatch):
    """`_submission_failures_view(session, user_id=N)` passes N to application_service."""
    from services import application_service
    from ui.routes import settings as settings_routes

    captured: dict[str, int] = {}

    async def _spy(session, *, user_id, **_):
        captured["user_id"] = user_id
        return []

    monkeypatch.setattr(application_service, "aggregate_submission_failures", _spy)

    asyncio.run(settings_routes._submission_failures_view(_NoopSession(), user_id=42))

    assert captured == {"user_id": 42}


def test_submission_failures_view_distinct_users_get_distinct_calls(monkeypatch):
    """Cross-user: user-1 + user-42 each thread their own id through."""
    from services import application_service
    from ui.routes import settings as settings_routes

    seen: list[int] = []

    async def _spy(session, *, user_id, **_):
        seen.append(user_id)
        return []

    monkeypatch.setattr(application_service, "aggregate_submission_failures", _spy)

    asyncio.run(settings_routes._submission_failures_view(_NoopSession(), user_id=1))
    asyncio.run(settings_routes._submission_failures_view(_NoopSession(), user_id=42))

    assert seen == [1, 42]


# ── _llm_cost_cap_view ───────────────────────────────────────────────────


def test_llm_cost_cap_view_threads_user_id(monkeypatch):
    """`_llm_cost_cap_view(session, settings, user_id=N)` passes N to llm_tracker."""
    from types import SimpleNamespace

    from services import llm_tracker
    from ui.routes import settings as settings_routes

    captured: dict[str, int] = {}

    async def _spy(session, *, user_id):
        captured["user_id"] = user_id
        return 0.0

    monkeypatch.setattr(llm_tracker, "today_cost_usd", _spy)

    settings = SimpleNamespace(daily_llm_cost_cap_usd=5.0)
    today, cap = asyncio.run(
        settings_routes._llm_cost_cap_view(_NoopSession(), settings, user_id=42)
    )

    assert captured == {"user_id": 42}
    assert today == 0.0
    assert cap == 5.0


def test_llm_cost_cap_view_distinct_users_get_distinct_calls(monkeypatch):
    """Cross-user: user-1 + user-42 each thread their own id through."""
    from types import SimpleNamespace

    from services import llm_tracker
    from ui.routes import settings as settings_routes

    seen: list[int] = []

    async def _spy(session, *, user_id):
        seen.append(user_id)
        return float(user_id)

    monkeypatch.setattr(llm_tracker, "today_cost_usd", _spy)

    settings = SimpleNamespace(daily_llm_cost_cap_usd=None)
    today_1, _ = asyncio.run(
        settings_routes._llm_cost_cap_view(_NoopSession(), settings, user_id=1)
    )
    today_42, _ = asyncio.run(
        settings_routes._llm_cost_cap_view(_NoopSession(), settings, user_id=42)
    )

    assert seen == [1, 42]
    assert today_1 == 1.0
    assert today_42 == 42.0


# ── None-session guard (matches existing helper semantics) ───────────────


def test_recent_scrape_runs_view_none_session_returns_empty():
    """Fake-session (session=None) → returns []; no service call. Mirrors
    existing `_build_sources_view` raise-or-degrade pattern from plan 56."""
    from ui.routes import settings as settings_routes

    result = asyncio.run(
        settings_routes._recent_scrape_runs_view(None, user_id=1)
    )
    assert result == []


def test_submission_failures_view_none_session_returns_empty():
    from ui.routes import settings as settings_routes

    result = asyncio.run(
        settings_routes._submission_failures_view(None, user_id=1)
    )
    assert result == []


def test_llm_cost_cap_view_none_session_returns_cap_only():
    """Fake-session → (0.0, cap); cap still resolved from settings."""
    from types import SimpleNamespace

    from ui.routes import settings as settings_routes

    settings = SimpleNamespace(daily_llm_cost_cap_usd=7.5)
    today, cap = asyncio.run(
        settings_routes._llm_cost_cap_view(None, settings, user_id=1)
    )
    assert today == 0.0
    assert cap == 7.5
