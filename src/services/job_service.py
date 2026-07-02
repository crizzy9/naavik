"""Job CRUD + dedup-aware upsert + scrape-run lifecycle.

Per docs/design/JOB_MODEL.md § F (graduated from plan 27 § D.9). Phase 2.0.06
(Crawl4AI base), 2.0.11 (Discover UI), and 2.0.14 (n8n migration) all call
into this module — there is no raw-SQL fallback in the route layer.

`upsert_job` is the load-bearing helper: idempotent on
`(user_id, source, external_id)` per the partial-unique index created by
migration 0005, plus tier-3 cross-source fuzzy dedup via
`services.dedup.find_duplicate` (plan 34, 0.2.0.09) — when tier-1 misses
and the incoming `(company, role)` matches a live cross-source Job
≥ threshold, the new row lands with `duplicate_of_id` set.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import (
    ApplicationBoard,
    Job,
    JobCreate,
    JobFilter,
    JobQueueState,
    JobScrapeRun,
    JobScrapeStatus,
    JobSource,
    RemotePolicy,
    VisaRestriction,
)
from services import dedup

# ── Single-job CRUD ──────────────────────────────────────────────────────


async def get_job(session: AsyncSession, job_id: int) -> Job | None:
    """Return Job by id (including soft-deleted rows; caller filters)."""
    stmt = select(Job).where(Job.id == job_id)
    return (await session.exec(stmt)).one_or_none()


async def list_jobs(
    session: AsyncSession,
    *,
    user_id: int,
    filters: JobFilter | None = None,
    page: int = 0,
    page_size: int = 50,
) -> list[Job]:
    """Filtered Job list, honoring soft-delete + ordered by score then recency.

    Per plan 27 § D.9: `ORDER BY score DESC, found_at DESC`, soft-deleted rows
    excluded, multi-tenant boundary applied via `user_id` filter.
    """
    if filters is None:
        filters = JobFilter()

    stmt = select(Job).where(Job.user_id == user_id, Job.deleted_at.is_(None))

    if not filters.include_duplicates:
        stmt = stmt.where(Job.duplicate_of_id.is_(None))

    if filters.company is not None:
        stmt = stmt.where(Job.company == filters.company)
    if filters.source is not None:
        stmt = stmt.where(Job.source == filters.source)
    if filters.board is not None:
        stmt = stmt.where(Job.board == filters.board)
    if filters.visa is not None:
        stmt = stmt.where(Job.visa_restrictions == filters.visa)
    if filters.remote_only:
        stmt = stmt.where(Job.remote_policy == RemotePolicy.REMOTE)
    if filters.seniority is not None:
        stmt = stmt.where(Job.seniority_level == filters.seniority)
    if filters.queue_state is not None:
        stmt = stmt.where(Job.queue_state == filters.queue_state)
    if filters.score_min > 0.0:
        stmt = stmt.where(Job.score >= filters.score_min)
    if filters.score_max < 1.0:
        stmt = stmt.where(Job.score <= filters.score_max)

    stmt = (
        stmt.order_by(Job.score.desc(), Job.found_at.desc())
        .offset(page * page_size)
        .limit(page_size)
    )
    rows = (await session.exec(stmt)).all()
    return list(rows)


async def archive_job(session: AsyncSession, job_id: int, *, user_id: int) -> None:
    """Soft-delete: sets `deleted_at = now()`. No-op if already archived.

    Raises ``PermissionError`` when ``job.user_id != user_id`` (closes the
    0.7.0.15 IDOR row — UI handlers that wire skip/save / archive actions
    must thread the authenticated user through this gate so a Job belonging
    to user A cannot be archived by user B via a crafted URL).
    """
    job = await get_job(session, job_id)
    if job is None or job.deleted_at is not None:
        return
    if job.user_id != user_id:
        raise PermissionError(f"job {job_id} does not belong to user {user_id}")
    now = datetime.now(UTC)
    job.deleted_at = now
    job.updated_at = now
    session.add(job)
    await session.flush()


async def restore_job(session: AsyncSession, job_id: int, *, user_id: int) -> Job:
    """Inverse of archive_job; clears `deleted_at`.

    Raises ``PermissionError`` when ``job.user_id != user_id`` (closes
    0.7.0.15 IDOR — symmetric guard with ``archive_job``).

    Raises ``ValueError`` if a live row with the same
    ``(user_id, source, external_id)`` already occupies the dedup slot —
    the partial-unique index permits a soft-deleted row to coexist with
    one live row, but un-archiving would push the count to two and trip
    the constraint at flush time. Caller must either archive the colliding
    live row first or accept the raise.
    """
    job = await get_job(session, job_id)
    if job is None:
        raise ValueError(f"job {job_id} not found")
    if job.user_id != user_id:
        raise PermissionError(f"job {job_id} does not belong to user {user_id}")
    if job.deleted_at is None:
        return job

    collision_stmt = select(Job).where(
        Job.user_id == job.user_id,
        Job.source == job.source,
        Job.external_id == job.external_id,
        Job.deleted_at.is_(None),
        Job.id != job.id,
    )
    if (await session.exec(collision_stmt)).one_or_none() is not None:
        raise ValueError(
            f"cannot restore job {job_id}: live row already occupies "
            f"(source={job.source.value}, external_id={job.external_id})"
        )

    now = datetime.now(UTC)
    job.deleted_at = None
    job.updated_at = now
    session.add(job)
    await session.flush()
    return job


# ── Manual job creation (+ Add by URL) ───────────────────────────────────


async def create_manual_job(
    session: AsyncSession,
    payload: JobCreate,
    *,
    user_id: int,
) -> Job:
    """Land a user-entered Job with synthetic `external_id`.

    `source = MANUAL`; `external_id = f"manual-{uuid4().hex[:12]}"` (plan 27
    § D.3 mandates synthetic id so the partial-unique index has a non-null
    value per row).
    """
    now = datetime.now(UTC)
    job = Job(
        user_id=user_id,
        source=JobSource.MANUAL,
        board=payload.board,
        external_id=f"manual-{uuid.uuid4().hex[:12]}",
        url=payload.url,
        url_type="external" if payload.board == ApplicationBoard.MANUAL else "ats",
        company=payload.company,
        role=payload.role,
        team=payload.team,
        location=payload.location,
        remote_policy=payload.remote_policy,
        seniority_level=payload.seniority_level,
        description=payload.description,
        visa_restrictions=payload.visa_restrictions,
        salary_min=payload.salary_min,
        salary_max=payload.salary_max,
        found_at=now,
        created_at=now,
        updated_at=now,
    )
    session.add(job)
    await session.flush()
    return job


# ── Scraper-pipeline upsert ──────────────────────────────────────────────


async def upsert_job(
    session: AsyncSession,
    *,
    user_id: int,
    source: JobSource,
    external_id: str,
    raw: dict,
    scrape_run_id: int | None = None,
) -> tuple[Job, bool]:
    """Idempotent on `(user_id, source, external_id)`. Returns `(job, created)`.

    On hit, refreshes `description_extracted_at`, merges `raw_meta`, and
    bumps `last_scrape_run_id`. On miss, runs tier-3 fuzzy dedup
    (plan 34 § D.7) — when the incoming `(company, role)` matches a live
    cross-source Job at score ≥ 88.0, the new row lands with
    `duplicate_of_id` pointing at the canonical existing row.

    `raw` is the scraper's normalized payload — required keys depend on
    whether the row is being created or updated. Create-path required keys:
    `board`, `url`, `url_type`, `company`, `role`, `description`. Optional
    keys map onto the SQLModel field of the same name when present. Unknown
    keys are dropped (kept off-row).
    """
    existing_stmt = select(Job).where(
        Job.user_id == user_id,
        Job.source == source,
        Job.external_id == external_id,
        Job.deleted_at.is_(None),
    )
    existing = (await session.exec(existing_stmt)).one_or_none()

    now = datetime.now(UTC)
    if existing is None:
        # Tier-3 fuzzy dedup (plan 34) — only fires when tier-1 missed.
        company = raw.get("company")
        role = raw.get("role")
        duplicate_of_id: int | None = None
        if company and role:
            match = await dedup.find_duplicate(
                session,
                user_id=user_id,
                company=company,
                role=role,
                source=source,
            )
            if match is not None:
                duplicate_of_id = match.id

        job = Job(
            user_id=user_id,
            source=source,
            external_id=external_id,
            **_create_payload(raw),
            duplicate_of_id=duplicate_of_id,
            found_at=now,
            created_at=now,
            updated_at=now,
        )
        if scrape_run_id is not None:
            job.last_scrape_run_id = scrape_run_id
        session.add(job)
        await session.flush()
        return job, True

    # Existing — refresh extraction metadata, merge raw_meta, bump last_scrape_run_id.
    existing.description_extracted_at = now
    existing.updated_at = now
    incoming_meta = raw.get("raw_meta") or {}
    if incoming_meta:
        existing.raw_meta = {**(existing.raw_meta or {}), **incoming_meta}
    if scrape_run_id is not None:
        existing.last_scrape_run_id = scrape_run_id
    session.add(existing)
    await session.flush()
    return existing, False


_JOB_CREATE_FIELDS = frozenset(
    {
        "board",
        "url",
        "url_type",
        "company",
        "role",
        "team",
        "location",
        "remote_policy",
        "seniority_level",
        "posted_at",
        "posted_at_text",
        "description",
        "description_html",
        "description_extracted_at",
        "description_extraction_model",
        "criteria",
        "skills_required",
        "visa_restrictions",
        "salary_min",
        "salary_max",
        "equity_pct",
        "score",
        "score_explanation",
        "match_breakdown",
        "queue_state",
        "tags",
        "warm_intro_contact_id",
        "raw_meta",
    }
)


def _create_payload(raw: dict) -> dict:
    """Project a scraper's `raw` dict onto Job-creatable fields.

    Drops unknown keys + supplies typed defaults for fields the scraper
    legitimately can omit (`remote_policy`, `visa_restrictions`).
    """
    out = {k: v for k, v in raw.items() if k in _JOB_CREATE_FIELDS}
    out.setdefault("remote_policy", RemotePolicy.UNKNOWN)
    out.setdefault("visa_restrictions", VisaRestriction.NOT_MENTIONED)
    out.setdefault("criteria", [])
    out.setdefault("skills_required", [])
    out.setdefault("tags", [])
    out.setdefault("match_breakdown", {})
    out.setdefault("raw_meta", {})
    return out


# ── Aggregates + scrape-run lifecycle ────────────────────────────────────


async def list_new_jobs_from_run(
    session: AsyncSession,
    *,
    run_id: int,
    limit: int = 5,
) -> list[Job]:
    """Return up to `limit` non-duplicate, live Jobs scoped to one scrape run.

    Plan 37 / 0.2.0.12 § A: per-run summary fetch helper. Orders by
    `found_at DESC` (most-recent first). Filters: `last_scrape_run_id ==
    run_id`, soft-delete-aware (`deleted_at IS NULL`), excludes tier-3
    cross-source duplicates (`duplicate_of_id IS NULL`).
    """
    stmt = (
        select(Job)
        .where(
            Job.last_scrape_run_id == run_id,
            Job.deleted_at.is_(None),
            Job.duplicate_of_id.is_(None),
        )
        .order_by(Job.found_at.desc())
        .limit(limit)
    )
    rows = (await session.exec(stmt)).all()
    return list(rows)


async def count_jobs_by_source(session: AsyncSession, user_id: int) -> dict[JobSource, int]:
    """Count of live Jobs per source for the user.

    Used by `/standup` + the future Scrapes panel. Soft-deleted rows are
    excluded. Sources with zero rows are omitted from the result.
    """
    from sqlalchemy import func

    stmt = (
        select(Job.source, func.count(Job.id))
        .where(Job.user_id == user_id, Job.deleted_at.is_(None))
        .group_by(Job.source)
    )
    rows = (await session.exec(stmt)).all()
    out: dict[JobSource, int] = {}
    for row in rows:
        # `session.exec` over a `select(col, func)` yields tuples even via
        # SQLModel; unpack defensively.
        if isinstance(row, tuple):
            source, count = row
        else:
            source, count = row[0], row[1]
        out[source] = int(count)
    return out


async def get_scrape_run(session: AsyncSession, scrape_run_id: int) -> JobScrapeRun | None:
    """Single JobScrapeRun by id — used by `/jobs/{id}` to render last-run metadata."""
    stmt = select(JobScrapeRun).where(JobScrapeRun.id == scrape_run_id)
    return (await session.exec(stmt)).one_or_none()


async def count_jobs_in_queue_state(
    session: AsyncSession, *, user_id: int, state: JobQueueState
) -> int:
    """Live count of the user's jobs in one queue state (Discover stats strip)."""
    from sqlalchemy import func

    stmt = (
        select(func.count())
        .select_from(Job)
        .where(Job.user_id == user_id, Job.queue_state == state, Job.deleted_at.is_(None))
    )
    return int((await session.exec(stmt)).one() or 0)


async def sum_listings_scanned_since(
    session: AsyncSession, *, user_id: int, since: datetime
) -> int:
    """Total listings returned by the user's scrape runs since `since`.

    Feeds the Discover "N scanned today" figure — real run telemetry, not a
    hardcoded placeholder.
    """
    from sqlalchemy import func

    stmt = select(func.coalesce(func.sum(JobScrapeRun.listings_returned), 0)).where(
        JobScrapeRun.user_id == user_id,
        JobScrapeRun.started_at >= since,
    )
    return int((await session.exec(stmt)).one() or 0)


async def list_recent_scrape_runs(
    session: AsyncSession,
    *,
    user_id: int,
    limit: int = 50,
) -> list[JobScrapeRun]:
    """Return up to ``limit`` most-recent JobScrapeRun rows for the user.

    Plan 54 / 0.2.5.04. Drives the Settings · Sources panel's
    "recent runs" history table. Ordered by ``started_at DESC``.
    Caller projects via `JobScrapeRunRead.model_validate` before rendering —
    defense-in-depth against any future `raw_meta` exposure in templates.
    """
    stmt = (
        select(JobScrapeRun)
        .where(JobScrapeRun.user_id == user_id)
        .order_by(JobScrapeRun.started_at.desc())
        .limit(limit)
    )
    rows = (await session.exec(stmt)).all()
    return list(rows)


async def list_recent_scrape_runs_by_source(
    session: AsyncSession,
    *,
    user_id: int,
) -> dict[JobSource, JobScrapeRun]:
    """Return the latest JobScrapeRun per source for the user.

    Per plan 49 / 0.2.0.16 § D.4. Drives the Settings · Sources panel's
    last-run timestamp + status chip per row. Postgres path uses
    `DISTINCT ON (source) ... ORDER BY source, started_at DESC` for a
    single-statement projection; sqlite test backend falls back to a
    two-statement approach (max(started_at) GROUP BY source, then fetch
    the matching rows) since `DISTINCT ON` is Postgres-only.
    """
    from sqlalchemy import func

    dialect_name = (
        session.bind.dialect.name
        if session.bind is not None and hasattr(session.bind, "dialect")
        else ""
    )

    if dialect_name == "postgresql":
        stmt = (
            select(JobScrapeRun)
            .where(JobScrapeRun.user_id == user_id)
            .order_by(JobScrapeRun.source, JobScrapeRun.started_at.desc())
            .distinct(JobScrapeRun.source)
        )
        rows = (await session.exec(stmt)).all()
        return {row.source: row for row in rows}

    max_stmt = (
        select(JobScrapeRun.source, func.max(JobScrapeRun.started_at))
        .where(JobScrapeRun.user_id == user_id)
        .group_by(JobScrapeRun.source)
    )
    max_rows = (await session.exec(max_stmt)).all()
    pairs: list[tuple[JobSource, datetime]] = []
    for row in max_rows:
        if isinstance(row, tuple):
            source, started = row
        else:
            source, started = row[0], row[1]
        pairs.append((source, started))
    if not pairs:
        return {}

    out: dict[JobSource, JobScrapeRun] = {}
    for source, started in pairs:
        stmt = (
            select(JobScrapeRun)
            .where(
                JobScrapeRun.user_id == user_id,
                JobScrapeRun.source == source,
                JobScrapeRun.started_at == started,
            )
            .limit(1)
        )
        result = (await session.exec(stmt)).one_or_none()
        if result is not None:
            out[source] = result
    return out


# ── Queue-state ops (plan 60 / 0.2.7.17) ─────────────────────────────────


async def set_queue_state(
    session: AsyncSession,
    job_id: int,
    *,
    user_id: int,
    state: JobQueueState,
) -> Job | None:
    """Flip a Job's `queue_state` (skip / save / queue-for-auto-apply).

    Replaces the in-memory `_set_job_queue_state` shim. Soft-delete-aware,
    user_id-scoped (IDOR boundary).
    """
    job = await get_job(session, job_id)
    if job is None or job.deleted_at is not None:
        return None
    if job.user_id != user_id:
        raise PermissionError(f"job {job_id} does not belong to user {user_id}")
    job.queue_state = state
    job.updated_at = datetime.now(UTC)
    session.add(job)
    await session.flush()
    return job


async def list_jobs_by_queue_state(
    session: AsyncSession,
    *,
    user_id: int,
    state: JobQueueState,
) -> list[Job]:
    """Thin wrapper around list_jobs filtered by queue_state.

    Used by `/api/v1/discover/saved` and `/api/v1/discover/skipped`.
    """
    return await list_jobs(
        session,
        user_id=user_id,
        filters=JobFilter(queue_state=state),
        page=0,
        page_size=200,
    )


async def auto_apply_queue(session: AsyncSession, *, user_id: int) -> list[Job]:
    """Jobs flipped to QUEUED_FOR_AUTO_APPLY for the user."""
    stmt = (
        select(Job)
        .where(
            Job.user_id == user_id,
            Job.queue_state == JobQueueState.QUEUED_FOR_AUTO_APPLY,
            Job.deleted_at.is_(None),
        )
        .order_by(Job.found_at.desc())
    )
    rows = (await session.exec(stmt)).all()
    return list(rows)


async def create_scraped_job_stub(
    session: AsyncSession,
    *,
    user_id: int,
    url: str,
    company: str,
    role: str,
) -> Job:
    """Land a placeholder Job from Discover · `+ Add by URL` modal.

    Stub for the 0.2.7.10 ATS-adapter follow-up. Until then, this synthesizes
    a high-score Job from the URL + (company, role) the operator supplied so
    Discover can render it immediately.
    """
    import hashlib

    now = datetime.now(UTC)
    ext = hashlib.sha1(url.encode()).hexdigest()[:12]
    job = Job(
        user_id=user_id,
        source=JobSource.MANUAL,
        board=ApplicationBoard.MANUAL,
        external_id=f"manual-{ext}",
        url=url,
        url_type="manual",
        company=company,
        role=role,
        team=None,
        location="San Francisco, CA",
        remote_policy=RemotePolicy.UNKNOWN,
        description="Scraped via + Add by URL.",
        visa_restrictions=VisaRestriction.NOT_MENTIONED,
        score=0.84,
        score_explanation="Auto-scored from manual URL submit.",
        queue_state=JobQueueState.UNSWIPED,
        found_at=now,
        created_at=now,
        updated_at=now,
    )
    session.add(job)
    await session.flush()
    return job


async def record_scrape_run(
    session: AsyncSession,
    *,
    user_id: int,
    source: JobSource,
    status: JobScrapeStatus,
    triggered_by: str = "cron",
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    requests_made: int = 0,
    listings_returned: int = 0,
    new_jobs: int = 0,
    updated_jobs: int = 0,
    errors: list[str] | None = None,
    raw_meta: dict | None = None,
) -> JobScrapeRun:
    """Append a JobScrapeRun row.

    `duration_ms` is computed from `started_at`/`finished_at` when both are
    present; otherwise left as None (a still-running scrape's row is
    insert-then-update; the final update sets `finished_at` + the lifecycle
    helper recomputes duration).
    """
    now = datetime.now(UTC)
    started = started_at or now
    duration_ms: int | None = None
    if finished_at is not None:
        duration_ms = int((finished_at - started).total_seconds() * 1000)

    run = JobScrapeRun(
        user_id=user_id,
        source=source,
        status=status,
        triggered_by=triggered_by,
        started_at=started,
        finished_at=finished_at,
        requests_made=requests_made,
        listings_returned=listings_returned,
        new_jobs=new_jobs,
        updated_jobs=updated_jobs,
        errors=list(errors or []),
        duration_ms=duration_ms,
        raw_meta=dict(raw_meta or {}),
        created_at=now,
    )
    session.add(run)
    await session.flush()
    return run
