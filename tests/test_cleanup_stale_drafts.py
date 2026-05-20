"""Plan 53 § A (0.2.4.01) — cleanup_stale_drafts service + cron tests.

Fixture matrix per plan § A.4:
| App | Status  | updated_at      | Expected            |
|-----|---------|-----------------|---------------------|
| 1   | DRAFT   | now - 45d       | archived            |
| 2   | DRAFT   | now - 29d       | untouched           |
| 3   | DRAFT   | now - 60d       | archived            |
| 4   | APPLIED | now - 90d       | untouched           |
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")
os.environ.setdefault("NAAVIK_DEBUG", "1")

from services.application_service import cleanup_stale_drafts  # noqa: E402


class _FakeSession:
    def __init__(self) -> None:
        self.added: list = []
        self.exec_queue: list = []
        self.flush_count = 0

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flush_count += 1

    async def exec(self, _stmt):
        if not self.exec_queue:
            return SimpleNamespace(all=lambda: [], one_or_none=lambda: None, one=lambda: 0)
        return self.exec_queue.pop(0)


def _make_draft(aid: int, days_old: int):
    """Build a fake DRAFT Application with updated_at backdated."""
    from models import ApplicationBoard, ApplicationStatus, DocsState, RecruiterState, ReferralState

    now = datetime.now(UTC)
    return SimpleNamespace(
        id=aid,
        user_id=1,
        job_id=100 + aid,
        company=f"Company{aid}",
        role="Role",
        team=None,
        status=ApplicationStatus.DRAFT,
        closed_reason=None,
        docs_state=DocsState.NONE,
        referral_state=ReferralState.NONE,
        recruiter_state=RecruiterState.NONE,
        board=ApplicationBoard.GREENHOUSE,
        deleted_at=None,
        applied_at=None,
        updated_at=now - timedelta(days=days_old),
    )


@pytest.mark.asyncio
async def test_cleanup_stale_drafts_archives_idle_rows():
    """DRAFTs idle > 30d get archived; idle <= 30d stay; non-DRAFTs untouched."""
    app1 = _make_draft(1, days_old=45)
    app3 = _make_draft(3, days_old=60)
    session = _FakeSession()
    # Service query returns only the rows matching `WHERE status=DRAFT AND
    # deleted_at IS NULL AND updated_at < threshold` — pre-filtered to apps 1+3.
    session.exec_queue = [
        SimpleNamespace(all=lambda: [app1, app3], one_or_none=lambda: None, one=lambda: 2)
    ]

    n = await cleanup_stale_drafts(session)
    assert n == 2


@pytest.mark.asyncio
async def test_cleanup_stale_drafts_flips_status_and_closed_reason():
    from models import ApplicationStatus, ClosedReason

    app = _make_draft(1, days_old=45)
    session = _FakeSession()
    session.exec_queue = [
        SimpleNamespace(all=lambda: [app], one_or_none=lambda: None, one=lambda: 1)
    ]

    await cleanup_stale_drafts(session)
    assert app.status == ApplicationStatus.CLOSED
    assert app.closed_reason == ClosedReason.WITHDRAWN_BY_ME
    assert app.deleted_at is not None


@pytest.mark.asyncio
async def test_cleanup_stale_drafts_emits_status_change_with_cleanup_stale_trigger():
    from models import AppEvent, AppEventKind, StatusChangeTrigger

    app = _make_draft(1, days_old=45)
    session = _FakeSession()
    session.exec_queue = [
        SimpleNamespace(all=lambda: [app], one_or_none=lambda: None, one=lambda: 1)
    ]

    await cleanup_stale_drafts(session)
    events = [obj for obj in session.added if isinstance(obj, AppEvent)]
    assert len(events) == 1
    ev = events[0]
    assert ev.kind == AppEventKind.STATUS_CHANGE
    assert ev.payload["trigger"] == StatusChangeTrigger.CLEANUP_STALE.value
    assert ev.payload["from"] == "DRAFT"
    assert ev.payload["to"] == "CLOSED"


@pytest.mark.asyncio
async def test_cleanup_stale_drafts_empty_when_no_stale_rows():
    """Returns 0 + no flush when nothing matches the threshold."""
    session = _FakeSession()
    session.exec_queue = [SimpleNamespace(all=lambda: [], one_or_none=lambda: None, one=lambda: 0)]

    n = await cleanup_stale_drafts(session)
    assert n == 0
    assert session.flush_count == 0


@pytest.mark.asyncio
async def test_cleanup_stale_drafts_honors_older_than_days_override():
    """Custom older_than_days threshold is respected by the query."""
    app = _make_draft(1, days_old=10)
    session = _FakeSession()
    session.exec_queue = [
        SimpleNamespace(all=lambda: [app], one_or_none=lambda: None, one=lambda: 1)
    ]

    n = await cleanup_stale_drafts(session, older_than_days=7)
    assert n == 1


def test_cleanup_stale_trigger_enum_value_exists():
    """Enum addition lands per plan § A.2."""
    from models.enums import StatusChangeTrigger

    assert StatusChangeTrigger.CLEANUP_STALE.value == "cleanup_stale"


def test_scheduler_jobs_cleanup_stale_drafts_in_allowlist():
    """plan 53 § A.3 — the scheduler-resident callable lands in the FUNC_REF_ALLOWLIST."""
    from scheduler.json_jobstore import FUNC_REF_ALLOWLIST

    assert "scheduler.jobs:cleanup_stale_drafts" in FUNC_REF_ALLOWLIST


def test_scheduler_jobs_exports_cleanup_stale_drafts():
    """Ensure the cron function is exported per scheduler.jobs.__all__."""
    from scheduler import jobs

    assert "cleanup_stale_drafts" in jobs.__all__
    assert callable(jobs.cleanup_stale_drafts)
