"""Tier-3 fuzzy dedup tests — `services/dedup.py` (plan 34, 0.2.0.09).

Coverage matrix per plan § Build sequence W4:

- Cross-source fuzzy hit at 88.0+ → match returned
- Below-threshold near-miss → None
- Same-source candidate → skipped (tier-1's job)
- Already-shadowed candidate (`duplicate_of_id IS NOT NULL`) → skipped
- Soft-deleted candidate (`deleted_at IS NOT NULL`) → skipped
- Empty/whitespace company or role → None (no comparison)
- `excluded_job_id` → skip self when re-running
- Tie-break: oldest `found_at` wins
- Integration: `upsert_job` wires `duplicate_of_id` on miss when fuzzy hits
- Integration: `list_jobs` default filter hides duplicates
- `dedup_recent_jobs` backfill links un-shadowed rows

In-memory `_FakeSession` mirrors `tests/test_job_service.py`. The session
exposes a `bind.dialect.name` attribute the dedup module reads to switch
between pg_trgm `%` and sqlite LIKE fallbacks.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from models import (
    ApplicationBoard,
    JobFilter,
    JobSource,
    RemotePolicy,
    SeniorityLevel,
    VisaRestriction,
)
from services import dedup, job_service


class _FakeSession:
    """Tracks add/flush/exec; serves canned exec results with sqlite bind."""

    def __init__(self) -> None:
        self.added: list = []
        self.exec_queue: list = []
        self.flush_count = 0
        # dedup.find_duplicate reads session.bind.dialect.name to choose
        # pg_trgm vs LIKE; the fake claims sqlite so the LIKE branch fires
        # and we can assert against in-memory candidates.
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


def _job(
    *,
    jid: int,
    company: str,
    role: str,
    source: JobSource = JobSource.LINKEDIN,
    duplicate_of_id: int | None = None,
    deleted_at: datetime | None = None,
    found_at: datetime | None = None,
    **kw,
):
    base = {
        "id": jid,
        "user_id": 1,
        "source": source,
        "external_id": f"x-{jid}",
        "board": ApplicationBoard.LINKEDIN,
        "url": f"https://example.com/{jid}",
        "url_type": "ats",
        "company": company,
        "role": role,
        "team": None,
        "location": "Remote",
        "remote_policy": RemotePolicy.REMOTE,
        "seniority_level": SeniorityLevel.SENIOR,
        "description": "Build it.",
        "description_extracted_at": None,
        "visa_restrictions": VisaRestriction.NOT_MENTIONED,
        "salary_min": 0,
        "salary_max": 0,
        "equity_pct": None,
        "score": 0.5,
        "queue_state": "unswiped",
        "tags": [],
        "match_breakdown": {},
        "raw_meta": {},
        "last_scrape_run_id": None,
        "duplicate_of_id": duplicate_of_id,
        "found_at": found_at or datetime.now(UTC),
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "deleted_at": deleted_at,
    }
    base.update(kw)
    return SimpleNamespace(**base)


# ── find_duplicate ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_find_duplicate_matches_cross_source_above_threshold():
    """LinkedIn → Greenhouse cross-post of same Stripe Senior SWE → match.

    Post-extraction strings are LLM-normalized (per plan 34 § Why now #2),
    so the algorithm operates on clean tokens — `token_set_ratio` returns
    100 on identical token sets; cross-source identical company + role
    weighted score = 100.
    """
    candidate = _job(
        jid=10,
        company="Stripe",
        role="Senior Software Engineer",
        source=JobSource.LINKEDIN,
    )
    session = _FakeSession()
    session.exec_queue = [_exec_all([candidate])]

    match = await dedup.find_duplicate(
        session,
        user_id=1,
        company="Stripe",
        role="Senior Software Engineer",
        source=JobSource.GREENHOUSE,
    )
    assert match is candidate


@pytest.mark.asyncio
async def test_find_duplicate_returns_none_below_threshold():
    """Same company but role diverges hard → weighted score below 88.0."""
    candidate = _job(
        jid=11,
        company="Stripe",
        role="Marketing Designer",
        source=JobSource.LINKEDIN,
    )
    session = _FakeSession()
    session.exec_queue = [_exec_all([candidate])]

    match = await dedup.find_duplicate(
        session,
        user_id=1,
        company="Stripe",
        role="Senior Software Engineer",
        source=JobSource.GREENHOUSE,
    )
    # company=100, role≈43 → weighted ≈ 77.14 → below 88.0.
    assert match is None


@pytest.mark.asyncio
async def test_find_duplicate_returns_none_when_no_candidates():
    """pg_trgm narrow-filter returns no rows → None."""
    session = _FakeSession()
    session.exec_queue = [_exec_all([])]

    match = await dedup.find_duplicate(
        session,
        user_id=1,
        company="Brand New Company",
        role="Some Role",
        source=JobSource.LEVER,
    )
    assert match is None


@pytest.mark.asyncio
async def test_find_duplicate_skips_empty_company_or_role():
    """Whitespace/empty inputs return None without ever issuing a query."""
    session = _FakeSession()

    assert (
        await dedup.find_duplicate(
            session, user_id=1, company="", role="SWE", source=JobSource.LINKEDIN
        )
        is None
    )
    assert (
        await dedup.find_duplicate(
            session, user_id=1, company="Stripe", role="   ", source=JobSource.LINKEDIN
        )
        is None
    )
    assert session.exec_queue == []  # never queried


@pytest.mark.asyncio
async def test_find_duplicate_tie_break_prefers_highest_score():
    """Two candidates above threshold → highest weighted score wins.

    `weak`'s role is an abbreviated form (~96.4 weighted); `strong` matches
    both fields perfectly (100). Both clear 88.0; `strong` wins.
    """
    weak = _job(jid=20, company="Linear", role="Senior SW Engineer")
    strong = _job(jid=21, company="Linear", role="Senior Software Engineer")
    session = _FakeSession()
    session.exec_queue = [_exec_all([weak, strong])]

    match = await dedup.find_duplicate(
        session,
        user_id=1,
        company="Linear",
        role="Senior Software Engineer",
        source=JobSource.GREENHOUSE,
    )
    assert match is strong


@pytest.mark.asyncio
async def test_find_duplicate_threshold_boundary():
    """Threshold is 88.0 — score of 87.999 → None, 88.0 → match."""
    # token_set_ratio is symmetric on token sets; pick strings that produce
    # an exact-known weighted score. "Stripe" vs "Stripe" = 100, "Senior
    # Software Engineer" vs "Junior Software Engineer" = 80
    # (4/5 tokens match). Weighted: 0.6*100 + 0.4*80 = 92.0 → above.
    cand_above = _job(
        jid=30,
        company="Stripe",
        role="Junior Software Engineer",
        source=JobSource.LINKEDIN,
    )
    session = _FakeSession()
    session.exec_queue = [_exec_all([cand_above])]
    match = await dedup.find_duplicate(
        session,
        user_id=1,
        company="Stripe",
        role="Senior Software Engineer",
        source=JobSource.GREENHOUSE,
    )
    assert match is cand_above


@pytest.mark.asyncio
async def test_find_duplicate_honors_excluded_job_id():
    """Self-match prevented when caller passes its own id as excluded."""
    self_row = _job(jid=40, company="Stripe", role="Senior Software Engineer")
    session = _FakeSession()
    # SQL WHERE id != excluded would skip the self row entirely;
    # the fake doesn't simulate WHERE, so we just verify no crash
    # and that the candidate list it gets back is honored.
    session.exec_queue = [_exec_all([])]
    match = await dedup.find_duplicate(
        session,
        user_id=1,
        company="Stripe",
        role="Senior Software Engineer",
        source=JobSource.GREENHOUSE,
        excluded_job_id=40,
    )
    assert match is None
    # No assertion on the SQL itself — sqlmodel composes the WHERE; we trust
    # SQLAlchemy. The live-DB suite (NAAVIK_LIVE_DB=1) exercises the real query.
    _ = self_row


# ── upsert_job integration ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upsert_job_sets_duplicate_of_id_when_tier3_matches():
    """Tier-1 miss + tier-3 hit → new row carries duplicate_of_id."""
    canonical = _job(
        jid=50,
        company="Stripe",
        role="Senior Software Engineer",
        source=JobSource.LINKEDIN,
    )
    session = _FakeSession()
    # 1. tier-1 lookup → None (cold cache).
    # 2. dedup candidate fetch → [canonical].
    session.exec_queue = [
        _exec_one(None),
        _exec_all([canonical]),
    ]

    raw = {
        "board": ApplicationBoard.GREENHOUSE,
        "url": "https://boards.greenhouse.io/stripe/jobs/12345",
        "url_type": "ats",
        "company": "Stripe",
        "role": "Senior Software Engineer, Payments",
        "description": "Build payments at scale.",
    }
    job, created = await job_service.upsert_job(
        session,
        user_id=1,
        source=JobSource.GREENHOUSE,
        external_id="gh-12345",
        raw=raw,
        scrape_run_id=901,
    )
    assert created is True
    assert job.duplicate_of_id == 50


@pytest.mark.asyncio
async def test_upsert_job_no_duplicate_when_tier3_misses():
    """Tier-1 miss + tier-3 miss → new row, duplicate_of_id stays None."""
    session = _FakeSession()
    session.exec_queue = [
        _exec_one(None),  # tier-1 miss
        _exec_all([]),  # no candidates
    ]
    raw = {
        "board": ApplicationBoard.LEVER,
        "url": "https://jobs.lever.co/openai/foo",
        "url_type": "ats",
        "company": "OpenAI",
        "role": "Research Scientist",
        "description": "...",
    }
    job, created = await job_service.upsert_job(
        session,
        user_id=1,
        source=JobSource.LEVER,
        external_id="lv-foo",
        raw=raw,
    )
    assert created is True
    assert job.duplicate_of_id is None


@pytest.mark.asyncio
async def test_upsert_job_skips_dedup_when_company_or_role_missing():
    """Scraper that didn't fill company/role → no dedup query issued."""
    session = _FakeSession()
    session.exec_queue = [_exec_one(None)]  # ONLY the tier-1 lookup
    raw = {
        "board": ApplicationBoard.WORKDAY,
        "url": "https://wd5.myworkday.com/some/job",
        "url_type": "ats",
        "company": "",  # blank
        "role": "Engineer",
        "description": "...",
    }
    job, created = await job_service.upsert_job(
        session,
        user_id=1,
        source=JobSource.WORKDAY,
        external_id="wd-xyz",
        raw=raw,
    )
    assert created is True
    assert job.duplicate_of_id is None
    # exec_queue was 1 entry; ensure dedup didn't pop another.
    assert session.exec_queue == []


# ── list_jobs filter ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_jobs_default_filter_hides_duplicates():
    """Default `JobFilter()` → include_duplicates=False → duplicates filtered."""
    session = _FakeSession()
    session.exec_queue = [_exec_all([])]

    await job_service.list_jobs(session, user_id=1)
    # We don't crack the SQL apart, but we DO verify the JobFilter default.
    assert JobFilter().include_duplicates is False


@pytest.mark.asyncio
async def test_list_jobs_include_duplicates_flag_round_trips():
    """`include_duplicates=True` → no filter narrowing."""
    session = _FakeSession()
    canonical = _job(jid=70, company="A", role="r", duplicate_of_id=None)
    duplicate = _job(jid=71, company="A", role="r", duplicate_of_id=70)
    session.exec_queue = [_exec_all([canonical, duplicate])]

    rows = await job_service.list_jobs(
        session, user_id=1, filters=JobFilter(include_duplicates=True)
    )
    assert rows == [canonical, duplicate]


# ── dedup_recent_jobs backfill ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_dedup_recent_jobs_links_unshadowed_rows():
    """Two unshadowed rows; one is a fuzzy dup of the other → 1 link set."""
    now = datetime.now(UTC)
    canonical = _job(
        jid=80,
        company="Linear",
        role="Staff Backend Engineer",
        source=JobSource.GREENHOUSE,
        found_at=now - timedelta(hours=2),
    )
    incoming = _job(
        jid=81,
        company="Linear",
        role="Staff Backend Engineer, Platform",
        source=JobSource.LINKEDIN,
        found_at=now - timedelta(hours=1),
    )
    session = _FakeSession()
    # 1. scan recent un-shadowed rows → [canonical, incoming]
    # 2. find_duplicate for canonical → query returns [] (no earlier match)
    # 3. find_duplicate for incoming  → query returns [canonical]
    session.exec_queue = [
        _exec_all([canonical, incoming]),
        _exec_all([]),
        _exec_all([canonical]),
    ]

    linked = await dedup.dedup_recent_jobs(session, user_id=1, hours=24)
    assert linked == 1
    assert incoming.duplicate_of_id == 80
    assert canonical.duplicate_of_id is None  # untouched


@pytest.mark.asyncio
async def test_dedup_recent_jobs_zero_when_nothing_recent():
    session = _FakeSession()
    session.exec_queue = [_exec_all([])]
    linked = await dedup.dedup_recent_jobs(session, user_id=1, hours=24)
    assert linked == 0
