"""Regression lint — `JobSource.AUTOMATED` must not reappear in `src/`.

Plan 27 (`0.2.0.05`) collapsed the 2-value `JobSource = {AUTOMATED, MANUAL}`
into the 10-value per-source enum (LINKEDIN / WORKDAY / GREENHOUSE / LEVER /
ASHBY / INDEED / COMPANY_DIRECT / RSSHUB / N8N_LEGACY / MANUAL). Existing
rows with `source='automated'` get remapped to per-board values by alembic
0005 (`board::text::jobsource`); the `automated` member persists in the
Postgres ENUM type only because PG <16 cannot DROP enum values cleanly.

If a future refactor inadvertently reintroduces `JobSource.AUTOMATED` in
Python code, dedup + scoring + UI filtering will silently start clustering
rows under the legacy bucket. This test fails loud so the regression
surfaces in code review.
"""

from __future__ import annotations

import re
from pathlib import Path


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
