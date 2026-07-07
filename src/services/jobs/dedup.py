"""Tier-3 fuzzy dedup — cross-source `(company, role)` match for Jobs.

Per docs/plans/34-0.2.0.09-job-dedup.md § D.2 + § D.4 (graduating to
docs/design/JOB_DEDUP.md). Tiers 1 (`(user_id, source, external_id)`
partial-unique) and 2 (`(user_id, url)` partial-unique) live structurally
in the schema (plan 27 migration 0005); tier 3 lives here.

Called inline from `job_service.upsert_job` BEFORE INSERT (and only when
tier-1 missed), so cross-board cross-posting (LinkedIn + Greenhouse + Lever
all surfacing the same Stripe role) lands as N rows where the second + Nth
carry `duplicate_of_id = first.id`. Discover UI filters them out by default.

Algorithm:

1. pg_trgm GIN-indexed `%` filter on `lower(Job.company)` narrows the N-row
   user pool to ~5-20 candidates whose company string is trigram-similar
   to the incoming.
2. For each candidate, weighted rapidfuzz score:
   `0.6 * token_set_ratio(company) + 0.4 * token_set_ratio(role)`.
3. Return the highest-scoring candidate >= 88.0 (0-100 scale); else None.
   Tie-break: oldest `found_at` wins (we shadow the new row to point at the
   pre-existing canonical row).
"""

from __future__ import annotations

from rapidfuzz import fuzz
from sqlalchemy import text
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import Job, JobSource

DEDUP_SCORE_THRESHOLD: float = 88.0
DEDUP_COMPANY_WEIGHT: float = 0.6
DEDUP_ROLE_WEIGHT: float = 0.4
DEDUP_CANDIDATE_LIMIT: int = 20


async def find_duplicate(
    session: AsyncSession,
    *,
    user_id: int,
    company: str,
    role: str,
    source: JobSource,
    excluded_job_id: int | None = None,
) -> Job | None:
    """Find a tier-3 fuzzy match for the (company, role) pair, or None.

    Same-source matches are skipped (tier-1's partial-unique handles those).
    Already-shadowed candidates (`duplicate_of_id IS NOT NULL`) are skipped
    to keep the dedup graph one-hop deep.

    Postgres-only candidate filter: uses the pg_trgm `%` operator to narrow
    via the `ix_job_company_trgm` GIN index. On sqlite (test substrate w/o
    pg_trgm), falls back to a case-insensitive substring filter on the same
    column — sufficient for the in-memory test harness; production runs
    Postgres.
    """
    norm_company = company.strip().lower()
    norm_role = role.strip().lower()
    if not norm_company or not norm_role:
        return None

    dialect = session.bind.dialect.name if session.bind is not None else "postgresql"

    base = select(Job).where(
        Job.user_id == user_id,
        Job.deleted_at.is_(None),
        Job.duplicate_of_id.is_(None),
        Job.source != source,
    )
    if excluded_job_id is not None:
        base = base.where(Job.id != excluded_job_id)

    if dialect == "postgresql":
        stmt = base.where(text("lower(job.company) % :norm_company")).params(
            norm_company=norm_company
        )
    else:
        stmt = base.where(text("lower(job.company) LIKE :like_company")).params(
            like_company=f"%{norm_company[:8]}%"
        )

    stmt = stmt.order_by(Job.found_at.asc()).limit(DEDUP_CANDIDATE_LIMIT)
    candidates = (await session.exec(stmt)).all()

    best: tuple[float, Job] | None = None
    for cand in candidates:
        cs = fuzz.token_set_ratio(norm_company, (cand.company or "").strip().lower())
        rs = fuzz.token_set_ratio(norm_role, (cand.role or "").strip().lower())
        score = DEDUP_COMPANY_WEIGHT * cs + DEDUP_ROLE_WEIGHT * rs
        if score >= DEDUP_SCORE_THRESHOLD and (best is None or score > best[0]):
            best = (score, cand)

    return best[1] if best else None


# ── Enrichment merge (plan 95 § 3.10, slice 95k) ────────────────────────

# Machine-written stub descriptions (email receipt / detected process) are
# replaceable; human-typed manual descriptions are NEVER touched.
_STUB_DESCRIPTION_PREFIXES = (
    "Inferred from the application-confirmation email",
    "Tracked from the interview email",
)
_MERGE_SOURCES_KEY = "enriched_from_shadow_ids"

# Fill-if-empty columns per the § 3.10 field table (`tags` added — the
# scorer's tag floor needs it and it is strictly additive).
_FILL_IF_EMPTY_FIELDS = (
    "salary_min",
    "salary_max",
    "posted_at",
    "location",
    "board",
    "criteria",
    "skills_required",
    "tags",
)


def _is_stub_url(url: str | None) -> bool:
    return (url or "").startswith("manual://")


def _is_stub_description(text: str | None) -> bool:
    return (text or "").startswith(_STUB_DESCRIPTION_PREFIXES)


def _empty(value) -> bool:
    return value is None or value == [] or value == {} or value == ""


async def enrich_canonical(session: AsyncSession, *, canonical: Job, shadow: Job) -> bool:
    """Copy the shadow's substance onto the tracked canonical row (§ 3.10 C).

    Identity is the row the human's history hangs off; substance is whatever
    the freshest source saw. Field-level merge is append/upgrade-only:
    `source`, `external_id`, timestamps, `queue_state`, and Application
    links are NEVER touched — the application never re-points.

    Idempotent (a shadow is recorded in `raw_meta` and never merged twice)
    and one-hop (a row that is itself shadowed never acts as a source).
    Returns True when anything changed.
    """
    from datetime import UTC, datetime

    if canonical.id is None or shadow.id is None or canonical.id == shadow.id:
        return False
    if shadow.duplicate_of_id not in (None, canonical.id):
        return False  # one-hop invariant: not our shadow
    meta = dict(canonical.raw_meta or {})
    merged_ids = [int(i) for i in (meta.get(_MERGE_SOURCES_KEY) or [])]
    if shadow.id in merged_ids:
        return False  # idempotent re-run

    changed = False
    description_changed = False

    # url/url_type — replace only a manual:// stub. The shadow hands its URL
    # to the canonical and keeps a merged-stub pointer: the tier-2
    # `(user_id, url)` unique index must hold, and future scrapes of the
    # posting URL should tier-2-hit the CANONICAL row from now on. The
    # shadow moves first (own flush) so no statement transiently collides.
    if _is_stub_url(canonical.url) and shadow.url and not _is_stub_url(shadow.url):
        incoming_url, incoming_url_type = shadow.url, shadow.url_type
        shadow.url = f"manual://merged/{shadow.id}"
        shadow.url_type = "manual"
        session.add(shadow)
        await session.flush()
        canonical.url = incoming_url
        canonical.url_type = incoming_url_type
        changed = True

    # description — replace only the machine-written receipt/process stub.
    if (
        _is_stub_description(canonical.description)
        and shadow.description
        and not _is_stub_description(shadow.description)
    ):
        canonical.description = shadow.description
        if shadow.description_html:
            canonical.description_html = shadow.description_html
        changed = True
        description_changed = True

    for field_name in _FILL_IF_EMPTY_FIELDS:
        current = getattr(canonical, field_name, None)
        incoming = getattr(shadow, field_name, None)
        if _empty(current) and not _empty(incoming):
            setattr(canonical, field_name, incoming)
            changed = True
    # visa_restrictions' "empty" is the NOT_MENTIONED default, not None.
    from models.enums import VisaRestriction

    if (
        canonical.visa_restrictions == VisaRestriction.NOT_MENTIONED
        and shadow.visa_restrictions != VisaRestriction.NOT_MENTIONED
    ):
        canonical.visa_restrictions = shadow.visa_restrictions
        changed = True

    # apply-target resolution — take the shadow's when canonical unresolved.
    if not canonical.apply_url and shadow.apply_url:
        canonical.apply_url = shadow.apply_url
        canonical.apply_kind = shadow.apply_kind
        canonical.apply_resolved_at = shadow.apply_resolved_at
        canonical.apply_resolved_via = shadow.apply_resolved_via
        changed = True

    # Record the merge source even on a no-op pass so re-runs short-circuit.
    merged_ids.append(shadow.id)
    meta[_MERGE_SOURCES_KEY] = merged_ids
    canonical.raw_meta = meta
    now = datetime.now(UTC)
    canonical.updated_at = now
    session.add(canonical)

    if description_changed:
        # The substance changed materially → clear score/embedding; the
        # score-pending + embed crons re-queue on score==0 / missing row.
        canonical.score = 0.0
        breakdown = dict(canonical.match_breakdown or {})
        breakdown.pop("scored_at", None)
        canonical.match_breakdown = breakdown
        from models import JobEmbedding

        embedding = await session.get(JobEmbedding, canonical.id)
        if embedding is not None:
            await session.delete(embedding)

        # Timeline note on the linked application: why the docs went stale.
        from models import Application
        from services.applications.common import _emit_event

        applications = (
            await session.exec(
                select(Application).where(
                    Application.job_id == canonical.id,
                    Application.deleted_at.is_(None),
                )
            )
        ).all()
        from models.enums import AppEventKind

        for application in applications:
            await _emit_event(
                session,
                user_id=application.user_id,
                application_id=application.id,
                kind=AppEventKind.NOTE_ADDED,
                actor="job_dedup_merge",
                payload={
                    "note": (
                        "Job details enriched from a scraper re-find "
                        f"({shadow.source.value}) — description/salary/URL updated; "
                        "generated docs may be stale."
                    ),
                    "shadow_job_id": shadow.id,
                },
            )

    await session.flush()
    return changed


async def dedup_recent_jobs(
    session: AsyncSession,
    *,
    user_id: int,
    hours: int = 24,
) -> int:
    """Backfill `duplicate_of_id` on recent un-shadowed Jobs.

    Reserved for the 0.2.0.10 `jobs.dedup` cron + the one-off backfill an
    operator runs post-deploy when cross-source duplicates already exist in
    their DB (per plan 34 § D.6 round-trip note). Returns the count of new
    links established.
    """
    from datetime import UTC, datetime, timedelta

    threshold = datetime.now(UTC) - timedelta(hours=hours)
    stmt = (
        select(Job)
        .where(
            Job.user_id == user_id,
            Job.deleted_at.is_(None),
            Job.duplicate_of_id.is_(None),
            Job.found_at >= threshold,
        )
        .order_by(Job.found_at.asc())
    )
    rows = (await session.exec(stmt)).all()

    linked = 0
    for row in rows:
        match = await find_duplicate(
            session,
            user_id=user_id,
            company=row.company,
            role=row.role,
            source=row.source,
            excluded_job_id=row.id,
        )
        if match is not None and match.id != row.id:
            row.duplicate_of_id = match.id
            session.add(row)
            linked += 1
            # Plan 95 § 3.10 — a tracked stub (email/manual canonical) gets
            # the scraped row's substance, not just a shadow pointer.
            if match.source in (JobSource.EMAIL, JobSource.MANUAL):
                await enrich_canonical(session, canonical=match, shadow=row)

    if linked:
        await session.flush()
    return linked
