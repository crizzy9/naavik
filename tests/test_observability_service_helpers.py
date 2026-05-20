"""Plan 54 / 0.2.5 service-helper unit tests.

Direct call into the new service helpers (no FastAPI route layer). Verifies:

- `application_service.aggregate_submission_failures` filters by `user_id`,
  excludes soft-deleted + null-artifacts rows, orders by `count() DESC`.
- `llm_tracker.today_cost_usd` filters to midnight-UTC boundary +
  returns 0.0 (not None) on empty result.
- `job_service.list_recent_scrape_runs` orders DESC + honors `limit`.

These tests bypass the route-layer autouse patches in
`test_settings_observability_dashboards.py` by living in a separate module —
the autouse fixture is module-scoped.
"""

from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace

os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")


# ── 0.2.5.02 — aggregate_submission_failures ───────────────────────────


def test_aggregate_submission_failures_filters_user_id():
    """Compiled SQL embeds `application.user_id = :u`."""
    from services.application_service import aggregate_submission_failures

    captured: list = []

    class _CapturingSession:
        async def exec(self, stmt):
            captured.append(stmt)
            return SimpleNamespace(all=lambda: [])

    rows = asyncio.run(aggregate_submission_failures(_CapturingSession(), user_id=42, since_days=7))
    assert rows == []
    assert len(captured) == 1
    compiled = str(captured[0].compile(compile_kwargs={"literal_binds": True})).lower()
    assert "application.user_id" in compiled
    assert "= 42" in compiled


def test_aggregate_submission_failures_orders_by_count_desc():
    """ORDER BY count() DESC so the most common failure-kind sits first."""
    from services.application_service import aggregate_submission_failures

    captured: list = []

    class _CapturingSession:
        async def exec(self, stmt):
            captured.append(stmt)
            return SimpleNamespace(all=lambda: [])

    asyncio.run(aggregate_submission_failures(_CapturingSession(), user_id=1))
    compiled = str(captured[0].compile(compile_kwargs={"literal_binds": True})).lower()
    assert "order by" in compiled
    assert "desc" in compiled


def test_aggregate_submission_failures_excludes_soft_deleted_rows():
    """`deleted_at IS NULL` predicate present in compiled SQL."""
    from services.application_service import aggregate_submission_failures

    captured: list = []

    class _CapturingSession:
        async def exec(self, stmt):
            captured.append(stmt)
            return SimpleNamespace(all=lambda: [])

    asyncio.run(aggregate_submission_failures(_CapturingSession(), user_id=1))
    compiled = str(captured[0].compile(compile_kwargs={"literal_binds": True})).lower()
    assert "deleted_at is null" in compiled


def test_aggregate_submission_failures_excludes_null_submission_artifacts():
    """`submission_artifacts IS NOT NULL` predicate avoids phantom NULL bucket."""
    from services.application_service import aggregate_submission_failures

    captured: list = []

    class _CapturingSession:
        async def exec(self, stmt):
            captured.append(stmt)
            return SimpleNamespace(all=lambda: [])

    asyncio.run(aggregate_submission_failures(_CapturingSession(), user_id=1))
    compiled = str(captured[0].compile(compile_kwargs={"literal_binds": True})).lower()
    assert "submission_artifacts is not null" in compiled


def test_aggregate_submission_failures_unpacks_rows_to_dicts():
    """Tuple result rows project into the {board, failure_kind, count, latest_at} shape."""
    from datetime import UTC, datetime

    from models import ApplicationBoard
    from services.application_service import aggregate_submission_failures

    seed_rows = [
        (
            ApplicationBoard.GREENHOUSE,
            "captcha",
            14,
            datetime(2026, 5, 18, 14, 32, tzinfo=UTC),
        ),
        (ApplicationBoard.LEVER, "auth_required", 5, datetime(2026, 5, 19, tzinfo=UTC)),
    ]

    class _SeededSession:
        async def exec(self, stmt):
            return SimpleNamespace(all=lambda: seed_rows)

    out = asyncio.run(aggregate_submission_failures(_SeededSession(), user_id=1, since_days=30))
    assert out == [
        {
            "board": "greenhouse",
            "failure_kind": "captcha",
            "count": 14,
            "latest_at": datetime(2026, 5, 18, 14, 32, tzinfo=UTC),
        },
        {
            "board": "lever",
            "failure_kind": "auth_required",
            "count": 5,
            "latest_at": datetime(2026, 5, 19, tzinfo=UTC),
        },
    ]


# ── 0.2.5.03 — today_cost_usd ──────────────────────────────────────────


def test_today_cost_usd_filters_user_and_midnight():
    """Compiled SQL embeds `api_usage.user_id = :u AND occurred_at >= :midnight`."""
    from services.llm_tracker import today_cost_usd

    captured: list = []

    class _CapturingSession:
        async def exec(self, stmt):
            captured.append(stmt)
            return SimpleNamespace(one=lambda: (0.0,))

    rows = asyncio.run(today_cost_usd(_CapturingSession(), user_id=7))
    assert rows == 0.0
    assert len(captured) == 1
    compiled = str(captured[0].compile(compile_kwargs={"literal_binds": True})).lower()
    assert "api_usage.user_id" in compiled
    assert "= 7" in compiled
    # Midnight UTC literal in the bound timestamp — hour/min/sec all zero.
    assert "00:00:00" in compiled


def test_today_cost_usd_returns_float_zero_when_empty():
    """`COALESCE(SUM(...), 0.0)` → 0.0 on empty result set, not None."""
    from services.llm_tracker import today_cost_usd

    class _EmptySession:
        async def exec(self, stmt):
            return SimpleNamespace(one=lambda: (0.0,))

    out = asyncio.run(today_cost_usd(_EmptySession(), user_id=1))
    assert out == 0.0
    assert isinstance(out, float)


def test_today_cost_usd_sums_provided_rows():
    """Returns the summed float from the seeded row."""
    from services.llm_tracker import today_cost_usd

    class _SeededSession:
        async def exec(self, stmt):
            return SimpleNamespace(one=lambda: (12.34,))

    out = asyncio.run(today_cost_usd(_SeededSession(), user_id=1))
    assert out == pytest_approx(12.34)


def pytest_approx(value, tol: float = 1e-9):
    """Minimal pytest.approx shim without importing the global hook."""

    class _Approx:
        def __eq__(self, other):
            return abs(other - value) < tol

        def __repr__(self):
            return f"approx({value})"

    return _Approx()


# ── 0.2.5.04 — list_recent_scrape_runs ─────────────────────────────────


def test_list_recent_scrape_runs_orders_desc_limits_arg():
    """ORDER BY started_at DESC + LIMIT honored from kwarg."""
    from services.job_service import list_recent_scrape_runs

    captured: list = []

    class _CapturingSession:
        async def exec(self, stmt):
            captured.append(stmt)
            return SimpleNamespace(all=lambda: [])

    out = asyncio.run(list_recent_scrape_runs(_CapturingSession(), user_id=3, limit=25))
    assert out == []
    assert len(captured) == 1
    compiled = str(captured[0].compile(compile_kwargs={"literal_binds": True})).lower()
    assert "order by" in compiled
    assert "started_at desc" in compiled
    assert "limit 25" in compiled
    assert "= 3" in compiled


def test_list_recent_scrape_runs_defaults_to_50():
    """Default `limit=50` lands in compiled SQL when caller omits the kwarg."""
    from services.job_service import list_recent_scrape_runs

    captured: list = []

    class _CapturingSession:
        async def exec(self, stmt):
            captured.append(stmt)
            return SimpleNamespace(all=lambda: [])

    asyncio.run(list_recent_scrape_runs(_CapturingSession(), user_id=1))
    compiled = str(captured[0].compile(compile_kwargs={"literal_binds": True})).lower()
    assert "limit 50" in compiled


def test_list_recent_scrape_runs_returns_list_type():
    """Returns `list[...]`, not a SQLAlchemy result proxy."""
    from services.job_service import list_recent_scrape_runs

    class _EmptySession:
        async def exec(self, stmt):
            return SimpleNamespace(all=lambda: [])

    out = asyncio.run(list_recent_scrape_runs(_EmptySession(), user_id=1))
    assert isinstance(out, list)
