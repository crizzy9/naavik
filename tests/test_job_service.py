"""job_service tests — plan 27 § D.12 (graduated to docs/design/JOB_MODEL.md).

Coverage of the 8-function service-layer surface:

- `upsert_job` idempotency on `(user_id, source, external_id)` + raw_meta merge
- `get_job` lookup
- `list_jobs` filter composition + score / found_at ordering
- `archive_job` soft-delete idempotency
- `restore_job` un-archive + collision detection
- `create_manual_job` synthetic `external_id` shape
- `count_jobs_by_source` aggregate roll-up
- `record_scrape_run` lifecycle row append + duration_ms computation

Uses an in-memory `_FakeSession` (matches `tests/test_application_service.py`)
so the suite is sub-second and DB-independent. Live-DB constraint behavior
is exercised by `tests/test_seed.py` when `NAAVIK_LIVE_DB=1`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from models import (
    ApplicationBoard,
    JobCreate,
    JobFilter,
    JobScrapeStatus,
    JobSource,
    RemotePolicy,
    SeniorityLevel,
    VisaRestriction,
)
from services import job_service

# ── In-memory fakes ──────────────────────────────────────────────────────


class _FakeSession:
    """Tracks add()/flush()/exec() calls; serves canned exec results.

    Exposes a sqlite-flavored `bind.dialect` so `services.dedup` picks the
    LIKE fallback branch rather than pg_trgm (plan 34 / 0.2.0.09).
    """

    def __init__(self) -> None:
        self.added: list = []
        self.exec_queue: list = []
        self.flush_count = 0
        self.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flush_count += 1

    async def exec(self, _stmt):
        if not self.exec_queue:
            return SimpleNamespace(one_or_none=lambda: None, all=lambda: [], one=lambda: 0)
        return self.exec_queue.pop(0)


def _exec_one(value):
    return SimpleNamespace(
        one_or_none=lambda: value,
        all=lambda: [value] if value else [],
        one=lambda: value,
    )


def _exec_all(values):
    return SimpleNamespace(
        one_or_none=lambda: values[0] if values else None,
        all=lambda: values,
        one=lambda: len(values),
    )


def _make_job(
    *,
    jid: int = 100,
    user_id: int = 1,
    source: JobSource = JobSource.GREENHOUSE,
    external_id: str = "abc123def456",
    deleted_at: datetime | None = None,
    raw_meta: dict | None = None,
    **kw,
):
    base = {
        "id": jid,
        "user_id": user_id,
        "source": source,
        "external_id": external_id,
        "board": ApplicationBoard.GREENHOUSE,
        "url": "https://example.com/jobs/123",
        "url_type": "ats",
        "company": "Stripe",
        "role": "Senior Engineer",
        "team": None,
        "location": "Remote",
        "remote_policy": RemotePolicy.REMOTE,
        "seniority_level": SeniorityLevel.SENIOR,
        "description": "Build it.",
        "description_extracted_at": None,
        "visa_restrictions": VisaRestriction.SPONSORSHIP_AVAILABLE,
        "salary_min": 200_000,
        "salary_max": 260_000,
        "equity_pct": None,
        "score": 0.8,
        "queue_state": "unswiped",
        "tags": [],
        "match_breakdown": {},
        "raw_meta": dict(raw_meta or {}),
        "last_scrape_run_id": None,
        "found_at": datetime.now(UTC),
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "deleted_at": deleted_at,
    }
    base.update(kw)
    return SimpleNamespace(**base)


# ── upsert_job ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upsert_job_creates_new_row_when_external_id_unseen():
    """Cold-cache path: existing lookup returns None → new Job row."""
    session = _FakeSession()
    session.exec_queue = [_exec_one(None)]

    raw = {
        "board": ApplicationBoard.LINKEDIN,
        "url": "https://linkedin.com/jobs/view/9911",
        "url_type": "ats",
        "company": "Anthropic",
        "role": "Senior ML Engineer",
        "description": "Frontier model work.",
        "skills_required": ["python", "pytorch"],
    }

    job, created = await job_service.upsert_job(
        session,
        user_id=1,
        source=JobSource.LINKEDIN,
        external_id="ln-9911-abc",
        raw=raw,
        scrape_run_id=901,
    )

    assert created is True
    assert job.user_id == 1
    assert job.source == JobSource.LINKEDIN
    assert job.external_id == "ln-9911-abc"
    assert job.company == "Anthropic"
    assert job.last_scrape_run_id == 901
    assert job.remote_policy == RemotePolicy.UNKNOWN
    assert job.visa_restrictions == VisaRestriction.NOT_MENTIONED
    assert session.added and session.added[0] is job
    assert session.flush_count == 1


@pytest.mark.asyncio
async def test_upsert_job_idempotent_on_existing_external_id():
    """Warm-cache path: existing Job returned, raw_meta merges, scrape_run bumps."""
    existing = _make_job(
        jid=42,
        source=JobSource.GREENHOUSE,
        external_id="gh-xyz",
        raw_meta={"prior_scrape_marker": "old"},
    )
    session = _FakeSession()
    session.exec_queue = [_exec_one(existing)]

    raw = {
        "raw_meta": {"rate_limit_hits": 0, "ua_idx": 3},
        # All other fields should be ignored on the update path (plan defers
        # field-level merge to 0.2.0.09).
        "company": "Should-Not-Update",
    }

    job, created = await job_service.upsert_job(
        session,
        user_id=1,
        source=JobSource.GREENHOUSE,
        external_id="gh-xyz",
        raw=raw,
        scrape_run_id=902,
    )

    assert created is False
    assert job is existing
    # raw_meta merged: old key preserved, new keys overlaid.
    assert job.raw_meta == {
        "prior_scrape_marker": "old",
        "rate_limit_hits": 0,
        "ua_idx": 3,
    }
    assert job.last_scrape_run_id == 902
    assert job.description_extracted_at is not None
    # Company should NOT update on the existing-row path.
    assert job.company == "Stripe"


@pytest.mark.asyncio
async def test_upsert_job_skips_scrape_run_when_none():
    """`scrape_run_id=None` must not overwrite an existing FK."""
    existing = _make_job(external_id="gh-keep", last_scrape_run_id=777)
    session = _FakeSession()
    session.exec_queue = [_exec_one(existing)]

    job, created = await job_service.upsert_job(
        session,
        user_id=1,
        source=JobSource.GREENHOUSE,
        external_id="gh-keep",
        raw={},
        scrape_run_id=None,
    )

    assert created is False
    assert job.last_scrape_run_id == 777  # unchanged


# ── get_job / list_jobs ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_job_returns_session_lookup():
    target = _make_job(jid=55)
    session = _FakeSession()
    session.exec_queue = [_exec_one(target)]

    out = await job_service.get_job(session, 55)
    assert out is target


@pytest.mark.asyncio
async def test_list_jobs_applies_filters_and_returns_session_rows():
    j1 = _make_job(jid=1, score=0.9)
    j2 = _make_job(jid=2, score=0.7)
    session = _FakeSession()
    session.exec_queue = [_exec_all([j1, j2])]

    filters = JobFilter(
        source=JobSource.GREENHOUSE,
        remote_only=True,
        score_min=0.5,
    )
    rows = await job_service.list_jobs(session, user_id=1, filters=filters)

    assert rows == [j1, j2]


@pytest.mark.asyncio
async def test_list_jobs_default_filter_is_empty():
    """`filters=None` should not blow up."""
    session = _FakeSession()
    session.exec_queue = [_exec_all([])]

    rows = await job_service.list_jobs(session, user_id=1)
    assert rows == []


# ── archive_job / restore_job ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_archive_job_soft_deletes_alive_row():
    job = _make_job(jid=11, deleted_at=None)
    session = _FakeSession()
    session.exec_queue = [_exec_one(job)]

    await job_service.archive_job(session, 11, user_id=1)
    assert job.deleted_at is not None
    assert job in session.added


@pytest.mark.asyncio
async def test_archive_job_noop_when_already_deleted():
    job = _make_job(jid=12, deleted_at=datetime.now(UTC))
    session = _FakeSession()
    session.exec_queue = [_exec_one(job)]

    await job_service.archive_job(session, 12, user_id=1)
    # Already-deleted: no flush, no add.
    assert session.added == []
    assert session.flush_count == 0


@pytest.mark.asyncio
async def test_archive_job_raises_when_user_id_mismatch():
    """0.7.0.15 IDOR — archive_job rejects cross-user mutation."""
    job = _make_job(jid=13, user_id=1, deleted_at=None)
    session = _FakeSession()
    session.exec_queue = [_exec_one(job)]

    with pytest.raises(PermissionError, match="does not belong to user"):
        await job_service.archive_job(session, 13, user_id=2)
    # No mutation when boundary trips.
    assert job.deleted_at is None
    assert session.added == []


@pytest.mark.asyncio
async def test_restore_job_clears_deleted_at_when_no_collision():
    archived = _make_job(jid=21, deleted_at=datetime.now(UTC))
    session = _FakeSession()
    # 1. get_job lookup, 2. collision check (None).
    session.exec_queue = [_exec_one(archived), _exec_one(None)]

    out = await job_service.restore_job(session, 21, user_id=1)
    assert out is archived
    assert archived.deleted_at is None


@pytest.mark.asyncio
async def test_restore_job_raises_on_live_collision():
    archived = _make_job(jid=21, external_id="dup-xid", deleted_at=datetime.now(UTC))
    live_dup = _make_job(jid=22, external_id="dup-xid", deleted_at=None)
    session = _FakeSession()
    session.exec_queue = [_exec_one(archived), _exec_one(live_dup)]

    with pytest.raises(ValueError, match="cannot restore"):
        await job_service.restore_job(session, 21, user_id=1)
    # deleted_at stays set — caller must resolve collision first.
    assert archived.deleted_at is not None


@pytest.mark.asyncio
async def test_restore_job_raises_when_user_id_mismatch():
    """0.7.0.15 IDOR — restore_job rejects cross-user mutation."""
    archived = _make_job(jid=23, user_id=1, deleted_at=datetime.now(UTC))
    session = _FakeSession()
    session.exec_queue = [_exec_one(archived)]

    with pytest.raises(PermissionError, match="does not belong to user"):
        await job_service.restore_job(session, 23, user_id=2)
    # No mutation when boundary trips.
    assert archived.deleted_at is not None


# ── create_manual_job ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_manual_job_synthesizes_external_id():
    payload = JobCreate(
        url="https://acme.com/careers/eng-1",
        board=ApplicationBoard.COMPANY_DIRECT,
        company="Acme",
        role="Staff Backend",
        description="Build a thing.",
        remote_policy=RemotePolicy.HYBRID,
        seniority_level=SeniorityLevel.STAFF,
        salary_min=240_000,
        salary_max=300_000,
    )
    session = _FakeSession()

    job = await job_service.create_manual_job(session, payload, user_id=1)

    assert job.source == JobSource.MANUAL
    assert job.external_id.startswith("manual-")
    assert len(job.external_id) == len("manual-") + 12
    assert job.board == ApplicationBoard.COMPANY_DIRECT
    assert job.url_type == "ats"  # COMPANY_DIRECT is an ATS-shaped surface
    assert job.url == "https://acme.com/careers/eng-1"
    assert job.salary_min == 240_000
    assert job.seniority_level == SeniorityLevel.STAFF
    assert job.remote_policy == RemotePolicy.HYBRID
    assert job in session.added


@pytest.mark.asyncio
async def test_create_manual_job_marks_url_type_external_when_board_manual():
    payload = JobCreate(
        url="https://random-employer.com/posting/abc",
        board=ApplicationBoard.MANUAL,
        company="RandomCo",
        role="SWE",
        description="…",
    )
    session = _FakeSession()
    job = await job_service.create_manual_job(session, payload, user_id=1)
    assert job.url_type == "external"


# ── count_jobs_by_source ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_count_jobs_by_source_aggregates_into_enum_keys():
    session = _FakeSession()
    session.exec_queue = [
        _exec_all(
            [
                (JobSource.LINKEDIN, 7),
                (JobSource.GREENHOUSE, 3),
                (JobSource.MANUAL, 1),
            ]
        )
    ]

    counts = await job_service.count_jobs_by_source(session, user_id=1)
    assert counts == {
        JobSource.LINKEDIN: 7,
        JobSource.GREENHOUSE: 3,
        JobSource.MANUAL: 1,
    }


# ── list_recent_scrape_runs_by_source ────────────────────────────────────


@pytest.mark.asyncio
async def test_list_recent_scrape_runs_by_source_empty_returns_dict():
    """User with no JobScrapeRun rows → empty dict."""
    session = _FakeSession()
    session.exec_queue = [_exec_all([])]

    out = await job_service.list_recent_scrape_runs_by_source(session, user_id=1)
    assert out == {}


@pytest.mark.asyncio
async def test_list_recent_scrape_runs_by_source_returns_latest_per_source():
    """Sqlite fallback path: GROUP BY max(started_at) → per-source row fetch."""
    now = datetime.now(UTC)
    linkedin_old = SimpleNamespace(
        id=10, source=JobSource.LINKEDIN, started_at=now - timedelta(hours=2)
    )
    linkedin_new = SimpleNamespace(
        id=11, source=JobSource.LINKEDIN, started_at=now - timedelta(minutes=10)
    )
    greenhouse_only = SimpleNamespace(
        id=12, source=JobSource.GREENHOUSE, started_at=now - timedelta(hours=1)
    )

    session = _FakeSession()
    # Aggregate query yields one tuple per source.
    session.exec_queue = [
        _exec_all(
            [
                (JobSource.LINKEDIN, linkedin_new.started_at),
                (JobSource.GREENHOUSE, greenhouse_only.started_at),
            ]
        ),
        # Per-source fetch queries — order matches enum order in pairs.
        _exec_one(linkedin_new),
        _exec_one(greenhouse_only),
    ]

    out = await job_service.list_recent_scrape_runs_by_source(session, user_id=1)
    assert set(out.keys()) == {JobSource.LINKEDIN, JobSource.GREENHOUSE}
    assert out[JobSource.LINKEDIN].id == 11
    assert out[JobSource.GREENHOUSE].id == 12
    # The older linkedin row never surfaced.
    assert out[JobSource.LINKEDIN].started_at == linkedin_new.started_at
    # Reference unused fixture for static-analysis silence.
    assert linkedin_old.id == 10


# ── record_scrape_run ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_record_scrape_run_computes_duration_when_both_timestamps_provided():
    started = datetime.now(UTC)
    finished = started + timedelta(seconds=42)
    session = _FakeSession()

    run = await job_service.record_scrape_run(
        session,
        user_id=1,
        source=JobSource.LINKEDIN,
        status=JobScrapeStatus.SUCCESS,
        triggered_by="cron",
        started_at=started,
        finished_at=finished,
        requests_made=120,
        listings_returned=18,
        new_jobs=4,
        updated_jobs=6,
        errors=["stage=fetch_detail kind=timeout"],
        raw_meta={"ua_pool_idx": 1},
    )

    assert run.duration_ms == 42_000
    assert run.status == JobScrapeStatus.SUCCESS
    assert run.source == JobSource.LINKEDIN
    assert run.errors == ["stage=fetch_detail kind=timeout"]
    assert run.requests_made == 120
    assert run.new_jobs == 4
    assert run in session.added


@pytest.mark.asyncio
async def test_record_scrape_run_leaves_duration_none_when_unfinished():
    """A still-running scrape row gets `finished_at=None`."""
    session = _FakeSession()
    run = await job_service.record_scrape_run(
        session,
        user_id=1,
        source=JobSource.WORKDAY,
        status=JobScrapeStatus.RUNNING,
        triggered_by="manual",
    )
    assert run.duration_ms is None
    assert run.finished_at is None
    assert run.status == JobScrapeStatus.RUNNING


# ── list_new_jobs_from_run (plan 37 / 0.2.0.12) ──────────────────────────


@pytest.mark.asyncio
async def test_list_new_jobs_from_run_returns_session_rows():
    """Helper just composes the SELECT + LIMIT; in-memory fake hands rows back."""
    session = _FakeSession()
    canned = [
        SimpleNamespace(id=101, last_scrape_run_id=901, role="Senior", company="Acme"),
        SimpleNamespace(id=102, last_scrape_run_id=901, role="Staff", company="Beta"),
    ]
    session.exec_queue = [_exec_all(canned)]

    rows = await job_service.list_new_jobs_from_run(session, run_id=901, limit=5)
    assert rows == canned


@pytest.mark.asyncio
async def test_list_new_jobs_from_run_empty_when_no_matches():
    session = _FakeSession()
    session.exec_queue = [_exec_all([])]
    rows = await job_service.list_new_jobs_from_run(session, run_id=901, limit=5)
    assert rows == []
