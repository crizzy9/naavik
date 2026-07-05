"""Resolution pipeline — LinkedIn tiering, resolve_job, retry ladder, cron sweep, stats.

Split out of services/apply_site_resolver.py in plan 91 Phase 4.5;
behaviour unchanged. Internal calls to patched seams route through `svc()`
(the services.apply_site_resolver facade) so test interception keeps
working; LinkedIn-auth calls stay lazy through the linkedin_resolver
facade for the same reason.
"""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import UTC, datetime

import httpx
from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import ApplicationBoard, Job, JobSource
from services.resolution.board_probe import _fetch
from services.resolution.common import (
    _KIND_TO_BOARD,
    _LINKEDIN_DETAIL_BASE,
    _RETRY_BACKOFF,
    _RETRY_RESERVE,
    MAX_RESOLVE_ATTEMPTS,
    svc,
)
from services.resolution.url_rules import (
    ResolvedApply,
    _BoardPosting,
    ats_org_from_url,
    classify_apply_url,
)

log = logging.getLogger(__name__)


async def _fetch_guest_detail(job: Job):
    """Fetch + parse the LinkedIn guest job-detail page (offsite marker + slug + JD)."""
    from services import resolution as linkedin_resolver

    detail_url = (job.raw_meta or {}).get("detail_endpoint") or (
        f"{_LINKEDIN_DETAIL_BASE}{job.external_id}"
    )
    try:
        resp = await _fetch(detail_url, accept="text/html")
    except (httpx.HTTPError, OSError) as exc:
        log.info("linkedin guest fetch failed for job %s: %s", job.id, exc)
        return linkedin_resolver.parse_guest_detail(None)
    if resp is None or resp.status_code != 200 or not resp.text:
        return linkedin_resolver.parse_guest_detail(None)
    return linkedin_resolver.parse_guest_detail(resp.text)


async def _resolve_linkedin(
    job: Job,
    *,
    _cache: dict[str, list[_BoardPosting]] | None,
    auth,
) -> ResolvedApply:
    """Two-tier LinkedIn resolution: guest-slug discovery, then authenticated."""
    from services import resolution as linkedin_resolver

    guest = await svc()._fetch_guest_detail(job)
    if guest.is_offsite is False:
        return ResolvedApply(
            kind="easy_apply",
            apply_url=job.url,
            description_html=guest.description_html,
            description_text=guest.description_text,
            via="linkedin_guest",
        )

    # Tier A — the guest company slug is the real ATS org more often than not.
    # Prefer the guest page's FULL title over the scraper's normalized role —
    # the extra discriminator ("(GO)") is what disambiguates near-duplicate
    # postings on the same board.
    guest_slugs = [guest.company_slug] if guest.company_slug else []
    role_for_match = guest.posting_title or job.role
    discovered = await svc().discover_ats_posting(
        company=job.company,
        role=role_for_match,
        location=job.location,
        extra_slugs=guest_slugs,
        _cache=_cache,
    )
    if discovered is not None and discovered.ats_org and discovered.ats_org in guest_slugs:
        discovered.via = "linkedin_guest_slug"

    # A confident Tier-A hit wins immediately (cheap, no browser). But an
    # AMBIGUOUS one — the title match couldn't pick THE posting among
    # near-duplicates — defers to the authoritative authenticated path when
    # available: "never a guess when the authenticated path is available".
    confident = discovered is not None and not discovered.ambiguous
    if confident:
        return discovered

    # Tier B — authenticated LinkedIn exposes the real offsite apply URL.
    if auth is not None and guest.is_offsite is not False:
        resolved = await linkedin_resolver.resolve_via_auth(job, auth)
        if resolved is not None:
            # Voyager's companyApplyUrl can be a tracking wrapper or a careers
            # page that redirects onto the real ATS — normalize before trusting
            # the "company_site" classification.
            if resolved.kind == "company_site" and resolved.apply_url:
                final, kind = await svc().normalize_apply_url(resolved.apply_url)
                if final != resolved.apply_url:
                    resolved.original_apply_url = resolved.apply_url
                    resolved.apply_url = final
                if kind is not None:
                    resolved.kind = kind
                    resolved.ats_org = ats_org_from_url(final, kind)
            return resolved

    # Auth unavailable / yielded nothing — fall back to the best-effort Tier-A
    # guess (right company + board, possibly the wrong near-duplicate posting).
    if discovered is not None:
        return discovered

    # Unresolvable-external: keep the honest kind, but carry the guest JD so
    # thin descriptions still get enriched.
    return ResolvedApply(
        kind="external" if guest.is_offsite else "unknown",
        apply_url=None,
        description_html=guest.description_html,
        description_text=guest.description_text,
        via="unresolved",
    )


async def resolve_job(
    job: Job,
    *,
    _cache: dict[str, list[_BoardPosting]] | None = None,
    auth=None,
) -> ResolvedApply:
    """Resolve one job's real application target. Pure of session writes.

    `auth` (a `linkedin_resolver.AuthContext`) enables the expensive
    authenticated LinkedIn fallback; `None` (the default, e.g. email
    inference) keeps resolution to the cheap guest + public-API tiers.
    """
    # 1. The listing URL itself already lives on an ATS host (direct ATS
    #    scrapes, some MANUAL pastes, email receipts with posting links).
    direct = classify_apply_url(job.url)
    if direct is not None:
        return ResolvedApply(kind=direct, apply_url=job.url, via="direct")

    posting_url = (job.raw_meta or {}).get("posting_url")
    direct = classify_apply_url(posting_url)
    if direct is not None:
        return ResolvedApply(kind=direct, apply_url=posting_url, via="direct")

    if job.source == JobSource.LINKEDIN:
        return await _resolve_linkedin(job, _cache=_cache, auth=auth)

    if job.source in (JobSource.INDEED, JobSource.EMAIL, JobSource.MANUAL):
        discovered = await svc().discover_ats_posting(
            company=job.company, role=job.role, location=job.location, _cache=_cache
        )
        if discovered is not None:
            return discovered
        return ResolvedApply(kind="unknown", apply_url=None, via="unresolved")

    # Direct ATS scrape whose URL didn't pattern-match (rare) — trust board.
    if job.board in (
        ApplicationBoard.GREENHOUSE,
        ApplicationBoard.LEVER,
        ApplicationBoard.ASHBY,
        ApplicationBoard.WORKDAY,
    ):
        return ResolvedApply(kind=job.board.value, apply_url=job.url, via="board_trust")
    return ResolvedApply(kind="unknown", apply_url=None, via="unresolved")


def _schedule_or_settle(job: Job) -> None:
    """Enforce the no-silent-dead-end invariant after any stamp.

    An unresolved target (external/unknown with no URL) is either scheduled
    for the next backoff rung or terminalized as "exhausted"; anything else
    clears the retry schedule.
    """
    unresolved = job.apply_url is None and job.apply_kind in ("external", "unknown")
    if not unresolved:
        job.apply_next_resolve_at = None
        return
    attempts = job.apply_resolve_attempts or 0
    if attempts >= MAX_RESOLVE_ATTEMPTS:
        job.apply_resolved_via = "exhausted"
        job.apply_next_resolve_at = None
        return
    delay = _RETRY_BACKOFF[min(max(attempts - 1, 0), len(_RETRY_BACKOFF) - 1)]
    job.apply_next_resolve_at = datetime.now(UTC) + delay


def apply_resolution(job: Job, resolved: ResolvedApply, *, count_attempt: bool = True) -> None:
    """Stamp resolution onto the Job row (caller flushes/commits).

    `count_attempt=False` for stamps that aren't resolution attempts (the
    operator's manual paste). An operator-pasted target is ground truth —
    automation never overwrites `via="manual"`.
    """
    if job.apply_resolved_via == "manual" and resolved.via != "manual":
        return
    if count_attempt:
        job.apply_resolve_attempts = (job.apply_resolve_attempts or 0) + 1
    job.apply_url = resolved.apply_url
    job.apply_kind = resolved.kind
    job.apply_resolved_at = datetime.now(UTC)
    job.apply_resolved_via = resolved.via
    board = _KIND_TO_BOARD.get(resolved.kind)
    if board is not None and job.board != board:
        job.board = board
    if resolved.ats_org:
        job.raw_meta = {**(job.raw_meta or {}), "ats_org": resolved.ats_org}
    if resolved.original_apply_url and resolved.original_apply_url != resolved.apply_url:
        job.raw_meta = {**(job.raw_meta or {}), "apply_url_original": resolved.original_apply_url}
    _schedule_or_settle(job)
    job.updated_at = datetime.now(UTC)


def note_failed_attempt(job: Job) -> None:
    """Bookkeeping when a resolution attempt CRASHED (vs resolving to unknown).

    Counts the attempt and walks the same backoff ladder, so a persistently
    crashing job leaves the fresh queue instead of eating sweep budget forever.
    """
    job.apply_resolve_attempts = (job.apply_resolve_attempts or 0) + 1
    if job.apply_kind is None:
        job.apply_kind = "unknown"
        job.apply_resolved_via = "unresolved"
    job.apply_resolved_at = datetime.now(UTC)
    _schedule_or_settle(job)
    job.updated_at = datetime.now(UTC)


async def resolve_pending(
    session: AsyncSession,
    *,
    batch_size: int = 12,
    jitter: tuple[float, float] = (2.0, 5.0),
) -> int:
    """Cron sweep: resolve fresh jobs (`apply_kind IS NULL`), then due retries.

    Fresh discoveries come first, newest first — those are the ones the
    operator is swiping — minus a small reserve so due retries can't be
    starved on heavy scrape days. Retries drain oldest-due first.
    Jittered sleeps keep the LinkedIn guest endpoint + board APIs polite.
    Returns the number of jobs resolved to a definite kind (not unknown).
    """
    now = datetime.now(UTC)
    due_clause = (
        Job.apply_next_resolve_at.is_not(None),  # type: ignore[union-attr]
        Job.apply_next_resolve_at <= now,
        Job.deleted_at.is_(None),
    )
    due_count = (await session.exec(select(func.count()).select_from(Job).where(*due_clause))).one()
    reserve = min(int(due_count), _RETRY_RESERVE)

    fresh_stmt = (
        select(Job)
        .where(Job.apply_kind.is_(None), Job.deleted_at.is_(None))
        .order_by(Job.found_at.desc())
        .limit(max(batch_size - reserve, 0))
    )
    jobs = list((await session.exec(fresh_stmt)).all())
    if len(jobs) < batch_size and due_count:
        retry_stmt = (
            select(Job)
            .where(*due_clause)
            .order_by(Job.apply_next_resolve_at.asc(), Job.found_at.desc())
            .limit(batch_size - len(jobs))
        )
        jobs.extend((await session.exec(retry_stmt)).all())
    if not jobs:
        return 0

    # Authenticated LinkedIn fallback — only when a session is configured, and
    # budgeted so one sweep never opens a long train of authenticated tabs.
    from services import resolution as linkedin_resolver

    auth = (
        linkedin_resolver.AuthContext(remaining=3, jitter=jitter)
        if (linkedin_resolver.auth_available())
        else None
    )

    cache: dict[str, list[_BoardPosting]] = {}
    definite = 0
    for i, job in enumerate(jobs):
        if i > 0:
            await asyncio.sleep(random.uniform(*jitter))
        try:
            resolved = await svc().resolve_job(job, _cache=cache, auth=auth)
        except Exception as exc:  # noqa: BLE001 — sweep must not die on one job
            log.warning("apply-site resolution failed for job %s: %s", job.id, exc)
            note_failed_attempt(job)
            session.add(job)
            await session.flush()
            continue
        apply_resolution(job, resolved)
        # Discovery already carried the canonical JD — enrich for free while
        # we hold it (thin Indeed/email descriptions get the real posting).
        if resolved.description_html or resolved.description_text:
            from services import jd_enrichment

            jd_enrichment.maybe_apply_discovered_description(job, resolved)
        # A DRAFT created before resolution snapshotted the aggregator board —
        # re-point it at the resolved target so Submit dispatches correctly.
        from services import application_service

        await application_service.resync_draft_apply_target(session, job)
        session.add(job)
        await session.flush()
        if resolved.kind not in ("unknown", "external"):
            definite += 1
        log.info(
            "apply-site resolved job=%s company=%s kind=%s url=%s",
            job.id,
            job.company,
            resolved.kind,
            (resolved.apply_url or "")[:100],
        )
    return definite


async def resolver_stats(session: AsyncSession, *, user_id: int) -> dict:
    """Resolution counts for the Settings ops card. Alive rows only."""
    now = datetime.now(UTC)
    base = (Job.user_id == user_id, Job.deleted_at.is_(None))
    via_rows = (
        await session.exec(
            select(Job.apply_resolved_via, func.count())
            .where(*base)
            .group_by(Job.apply_resolved_via)
        )
    ).all()
    by_via = {via or "never": int(n) for via, n in via_rows}

    async def _count(*clauses) -> int:
        value = (
            await session.exec(select(func.count()).select_from(Job).where(*base, *clauses))
        ).one()
        return int(value or 0)  # `or 0`: the sample-data noop session yields None

    return {
        "by_via": by_via,
        "pending": await _count(Job.apply_kind.is_(None)),
        "retry_due": await _count(
            Job.apply_next_resolve_at.is_not(None),  # type: ignore[union-attr]
            Job.apply_next_resolve_at <= now,
        ),
        "retry_scheduled": await _count(
            Job.apply_next_resolve_at.is_not(None),  # type: ignore[union-attr]
            Job.apply_next_resolve_at > now,
        ),
        "exhausted": by_via.get("exhausted", 0),
        "resolved": await _count(Job.apply_url.is_not(None)),  # type: ignore[union-attr]
    }
