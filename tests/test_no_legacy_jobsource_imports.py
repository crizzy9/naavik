"""Regression lints around the Job pipeline + Discover UI.

Two checks live here, both load-bearing for plan 27 (`0.2.0.05`) +
plan 36 (`0.2.0.11`):

1. `JobSource.AUTOMATED` must not reappear in `src/` (plan 27 collapsed
   the 2-value enum into 10 per-source values; the legacy bucket would
   silently cluster rows if a future refactor re-typed it).
2. `src/ui/discover_ctx.py:build_discover_ctx` must remain wired to
   `services.job_service.list_jobs` (plan 36 cut the umbilical from
   `db.sample_data.discover_queue()` for the live-DB path). Sample data
   stays as a fallback for fake-session callers — but the
   `job_service.list_jobs` call MUST be present for the live path so the
   scraper crons' output surfaces in the swipe queue.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.uses_sample_data_shims


def test_no_legacy_jobsource_automated_in_src():
    src = Path(__file__).resolve().parent.parent / "src"
    pat = re.compile(r"\bJobSource\.AUTOMATED\b")
    offenders = [
        str(p.relative_to(src))
        for p in src.rglob("*.py")
        if pat.search(p.read_text(encoding="utf-8"))
    ]
    assert not offenders, (
        f"JobSource.AUTOMATED was removed in plan 27 (`0.2.0.05`); offenders: {offenders}. "
        "Use a per-source value (LINKEDIN/WORKDAY/GREENHOUSE/...) or MANUAL instead."
    )


def test_discover_ctx_wires_job_service_list_jobs():
    """Plan 36 § A — discover_ctx MUST call `job_service.list_jobs`.

    Guards against a future regression that re-routes the Discover queue
    back through `db.sample_data.discover_queue()` for the live-DB path
    (the legacy umbilical). Sample data is allowed as a fallback for
    fake-session callers; the live path is non-negotiable.
    """
    path = Path(__file__).resolve().parent.parent / "src" / "ui" / "discover_ctx.py"
    body = path.read_text(encoding="utf-8")
    assert "job_service.list_jobs" in body, (
        "src/ui/discover_ctx.py must call services.job_service.list_jobs for the "
        "live-DB path (plan 36 § A). If you're intentionally rolling back to the "
        "sample_data shim, update this lint + document the regression in the "
        "plan's ## Deviations section."
    )
    # Accept either a dedicated `from services import jobs as job_service` line, the
    # combined `from services import …, job_service, …` form (used after the
    # plan-69 service-layer expansion), or the long-form `from services.job_service`
    # alias. The lint exists to catch a regression to `sd.discover_queue()`, not
    # to police import grouping.
    import_pattern = re.compile(
        r"^\s*from\s+services\s+import\s+[^\n]*\bjob_service\b|"
        r"^\s*from\s+services\.job_service\s+import\b",
        re.MULTILINE,
    )
    assert import_pattern.search(body), (
        "src/ui/discover_ctx.py must import job_service (plan 36 § A wiring)."
    )
