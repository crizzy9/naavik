"""Apply-site resolution — where a job application ACTUALLY happens.

Aggregator listings (LinkedIn / Indeed) hand off to an external ATS, but the
scrapers stamp `board=LINKEDIN/INDEED`, so adapter dispatch, auto-apply
gating, and every "open posting" link pointed at the aggregator. This module
resolves the real application target per job:

1. Direct classification — the listing URL (or a receipt's posting URL)
   already lives on a known ATS host.
2. LinkedIn offsite probe — the public jobs-guest detail page says whether
   the Apply button is offsite (`apply-link-offsite` markers) or native
   Easy Apply. LinkedIn gates the offsite TARGET behind sign-in, so...
3. ATS discovery — probe the PUBLIC Greenhouse / Lever / Ashby board APIs
   with company-slug candidates and strict title matching. A hit yields the
   canonical posting URL (and the full JD, which enrichment reuses).

Resolution promotes `Job.board` when the kind maps to a known
ApplicationBoard, so downstream dispatch Just Works. All fetches are
SSRF-guarded (`scraper.url_guard`) with manual redirect re-checking.
"""

from __future__ import annotations

import asyncio
import difflib
import logging
import random
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import ApplicationBoard, Job, JobSource
from scraper.url_guard import is_safe_destination
from scraper.user_agents import pick_user_agent

log = logging.getLogger(__name__)

_FETCH_TIMEOUT = 12.0
_MAX_REDIRECTS = 5
_TITLE_MATCH_THRESHOLD = 0.72
# Two postings scoring within this of the winner is a tie the title match can't
# break — the caller should prefer an authoritative source over the guess.
_AMBIGUITY_EPS = 0.02

# UI labels double as the closed vocabulary for `Job.apply_kind`.
APPLY_KIND_LABELS: dict[str, str] = {
    "greenhouse": "Greenhouse",
    "lever": "Lever",
    "ashby": "Ashby",
    "workday": "Workday",
    "icims": "iCIMS",
    "smartrecruiters": "SmartRecruiters",
    "taleo": "Taleo",
    "bamboohr": "BambooHR",
    "recruitee": "Recruitee",
    "jobvite": "Jobvite",
    "breezy": "Breezy",
    "workable": "Workable",
    "easy_apply": "Easy Apply",
    "company_site": "Company site",
    "external": "External site",
    "unknown": "",  # honest: no chip when we could not classify
}

# Host-pattern → kind. Checked in order; first match wins.
_ATS_HOST_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("greenhouse", re.compile(r"(?:^|\.)greenhouse\.io$|^grnh\.se$")),
    ("lever", re.compile(r"^jobs\.(?:eu\.)?lever\.co$")),
    ("ashby", re.compile(r"^jobs\.ashbyhq\.com$")),
    ("workday", re.compile(r"\.myworkdayjobs\.com$|\.myworkdaysite\.com$")),
    ("icims", re.compile(r"\.icims\.com$")),
    ("smartrecruiters", re.compile(r"^(?:jobs|careers)\.smartrecruiters\.com$")),
    ("taleo", re.compile(r"\.taleo\.net$")),
    ("bamboohr", re.compile(r"\.bamboohr\.com$")),
    ("recruitee", re.compile(r"\.recruitee\.com$")),
    ("jobvite", re.compile(r"^jobs\.jobvite\.com$")),
    ("breezy", re.compile(r"\.breezy\.hr$")),
    ("workable", re.compile(r"^(?:apply|jobs)\.workable\.com$")),
)

# Kinds that map to an ApplicationBoard — resolution promotes Job.board so
# adapter dispatch + SUPPORTED_AUTO_SUBMIT_BOARDS gating follow the truth.
_KIND_TO_BOARD: dict[str, ApplicationBoard] = {
    "greenhouse": ApplicationBoard.GREENHOUSE,
    "lever": ApplicationBoard.LEVER,
    "ashby": ApplicationBoard.ASHBY,
    "workday": ApplicationBoard.WORKDAY,
    "easy_apply": ApplicationBoard.LINKEDIN,
    "company_site": ApplicationBoard.COMPANY_DIRECT,
}

_LINKEDIN_DETAIL_BASE = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/"

# Legal/noise suffixes stripped before slug candidates are built.
_COMPANY_NOISE = re.compile(
    r"\b(?:inc|llc|ltd|corp|corporation|co|gmbh|technologies|technology)\b\.?", re.IGNORECASE
)


@dataclass
class ResolvedApply:
    """Outcome of one resolution attempt (network already done)."""

    kind: str
    apply_url: str | None = None
    ats_org: str | None = None
    # Full JD captured for free during ATS discovery — enrichment's input.
    description_html: str | None = None
    description_text: str | None = None
    posting_title: str | None = None
    # Provenance — how we got here. Authoritative ("direct", "linkedin_guest_slug",
    # "linkedin_auth", "board_trust") vs guessed ("ats_discovery") vs "unresolved".
    via: str | None = None
    # Discovery tie: >=2 postings scored within an epsilon of the winner, so the
    # title match can't pick THE posting (e.g. two near-identical Boston SWE
    # roles). Transient signal — the LinkedIn branch prefers the authoritative
    # authenticated path over an ambiguous guess. Not persisted.
    ambiguous: bool = False


@dataclass
class _BoardPosting:
    title: str
    url: str
    location: str
    kind: str
    org: str
    description_html: str | None = None
    description_text: str | None = None


def classify_apply_url(url: str | None) -> str | None:
    """ATS kind for a URL on a known ATS host; None when unrecognized."""
    if not url:
        return None
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return None
    if not host:
        return None
    for kind, pattern in _ATS_HOST_PATTERNS:
        if pattern.search(host):
            return kind
    return None


def slug_candidates(company: str) -> list[str]:
    """Ordered org-slug guesses for public ATS board APIs (max 3)."""
    base = _COMPANY_NOISE.sub(" ", (company or "").lower())
    words = re.findall(r"[a-z0-9]+", base)
    if not words:
        return []
    out: list[str] = []
    joined = "".join(words)
    hyphenated = "-".join(words)
    for cand in (joined, hyphenated, words[0]):
        if cand and cand not in out:
            out.append(cand)
    return out[:3]


def _normalize_title(title: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (title or "").lower()))


def title_match_score(listing_title: str, posting_title: str) -> float:
    """Similarity in [0,1] — containment of the listing title boosts to 1.0."""
    a, b = _normalize_title(listing_title), _normalize_title(posting_title)
    if not a or not b:
        return 0.0
    if a == b or a in b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


# Aggregators love region-only locations ("North America") that never
# token-match a posting's city. A compact NA-city table breaks the tie —
# picking Edinburgh over Boston for a "North America" listing is a real
# mis-attach, not a cosmetic one.
_NA_REGION_HINTS = frozenset({"america", "states", "usa", "us", "canada", "national"})
_NA_CITIES = frozenset(
    {
        "boston",
        "york",
        "nyc",
        "francisco",
        "seattle",
        "austin",
        "denver",
        "chicago",
        "atlanta",
        "toronto",
        "vancouver",
        "mountain",
        "palo",
        "sunnyvale",
        "angeles",
        "diego",
        "jose",
        "miami",
        "dallas",
        "houston",
        "portland",
        "phoenix",
        "philadelphia",
        "washington",
        "raleigh",
        "durham",
        "nashville",
        "minneapolis",
        "columbus",
        "pittsburgh",
        "montreal",
        "salt",
        "boulder",
        "oakland",
        "bellevue",
        "redmond",
        "cambridge",
        "brooklyn",
        "irvine",
        "tempe",
        "remote",
    }
)


def _location_bonus(job_location: str | None, posting_location: str) -> float:
    """Tie-breaking bonus: exact token overlap 0.1, region agreement 0.05."""
    if not job_location or not posting_location:
        return 0.0
    a = set(re.findall(r"[a-z]+", job_location.lower()))
    b = set(re.findall(r"[a-z]+", posting_location.lower()))
    if (a - {"remote", "united", "states", "us", "usa"}) & b:
        return 0.1
    if a & _NA_REGION_HINTS and b & (_NA_CITIES | {"united", "states", "usa"}):
        return 0.05
    return 0.0


async def _fetch(url: str, *, accept: str = "application/json") -> httpx.Response | None:
    """SSRF-guarded GET with manual redirect re-checking (calendar_sync pattern)."""
    current = url
    headers = {"User-Agent": pick_user_agent(), "Accept": accept}
    async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT, follow_redirects=False) as client:
        for _ in range(_MAX_REDIRECTS + 1):
            safe, reason = is_safe_destination(current)
            if not safe:
                log.info("apply-site fetch blocked (%s): %s", reason, current[:120])
                return None
            resp = await client.get(current, headers=headers)
            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("location")
                if not location:
                    return None
                current = str(httpx.URL(current).join(location))
                continue
            return resp
    return None


async def _greenhouse_postings(org: str) -> list[_BoardPosting]:
    resp = await _fetch(f"https://boards-api.greenhouse.io/v1/boards/{org}/jobs?content=true")
    if resp is None or resp.status_code != 200:
        return []
    try:
        jobs = resp.json().get("jobs") or []
    except ValueError:
        return []
    return [
        _BoardPosting(
            title=j.get("title") or "",
            url=j.get("absolute_url") or "",
            location=((j.get("location") or {}).get("name")) or "",
            kind="greenhouse",
            org=org,
            description_html=j.get("content"),
        )
        for j in jobs
        if j.get("absolute_url")
    ]


async def _lever_postings(org: str) -> list[_BoardPosting]:
    resp = await _fetch(f"https://api.lever.co/v0/postings/{org}?mode=json")
    if resp is None or resp.status_code != 200:
        return []
    try:
        jobs = resp.json()
    except ValueError:
        return []
    if not isinstance(jobs, list):
        return []
    return [
        _BoardPosting(
            title=j.get("text") or "",
            url=j.get("hostedUrl") or "",
            location=((j.get("categories") or {}).get("location")) or "",
            kind="lever",
            org=org,
            description_text=j.get("descriptionPlain"),
            description_html=j.get("description"),
        )
        for j in jobs
        if isinstance(j, dict) and j.get("hostedUrl")
    ]


async def _ashby_postings(org: str) -> list[_BoardPosting]:
    resp = await _fetch(f"https://api.ashbyhq.com/posting-api/job-board/{org}")
    if resp is None or resp.status_code != 200:
        return []
    try:
        jobs = resp.json().get("jobs") or []
    except ValueError:
        return []
    out: list[_BoardPosting] = []
    for j in jobs:
        if not j.get("isListed", True):
            continue
        url = j.get("jobUrl") or j.get("applyUrl") or ""
        if not url:
            continue
        locations = [j.get("location") or ""] + [
            loc for loc in (j.get("secondaryLocations") or []) if isinstance(loc, str)
        ]
        out.append(
            _BoardPosting(
                title=j.get("title") or "",
                url=url,
                location=", ".join(x for x in locations if x),
                kind="ashby",
                org=org,
                description_html=j.get("descriptionHtml"),
            )
        )
    return out


def _sanitize_slug(value: str | None) -> str | None:
    """Accept a slug only if it's a clean org token (guest HTML can be noisy)."""
    if not value:
        return None
    slug = value.strip().lower()
    return slug if re.fullmatch(r"[a-z0-9][a-z0-9-]{0,60}", slug) else None


async def _fetch_slug_boards(slug: str) -> list[_BoardPosting]:
    """First non-empty of the Greenhouse/Lever/Ashby boards for one slug."""
    for fetcher in (_greenhouse_postings, _lever_postings, _ashby_postings):
        try:
            postings = await fetcher(slug)
        except (httpx.HTTPError, OSError) as exc:
            log.info("ATS discovery fetch failed for %s: %s", slug, exc)
            postings = []
        if postings:
            return postings
    return []


async def discover_ats_posting(
    *,
    company: str,
    role: str,
    location: str | None = None,
    extra_slugs: list[str] | None = None,
    _cache: dict[str, list[_BoardPosting]] | None = None,
) -> ResolvedApply | None:
    """Probe public Greenhouse/Lever/Ashby board APIs for this company+role.

    `extra_slugs` (e.g. the LinkedIn company-page slug parsed from the guest
    detail) are tried BEFORE the company-name guesses — they close the gap
    where the display name ("Catapult") never derives the ATS slug
    ("catapultsports"). Strict title matching (>= 0.72 similarity or
    containment) keeps us from attaching the WRONG posting — no hit beats a
    guessed hit. `_cache` reuses board fetches across a sweep, keyed by slug.
    """
    candidates: list[str] = []
    for raw in extra_slugs or []:
        slug = _sanitize_slug(raw)
        if slug and slug not in candidates:
            candidates.append(slug)
    for slug in slug_candidates(company):
        if slug not in candidates:
            candidates.append(slug)

    postings: list[_BoardPosting] = []
    for slug in candidates:
        if _cache is not None and slug in _cache:
            hit = _cache[slug]
        else:
            hit = await _fetch_slug_boards(slug)
            if _cache is not None:
                _cache[slug] = hit
        if hit:
            postings = hit
            break
    if not postings:
        return None

    scored = [
        (title_match_score(role, p.title) + _location_bonus(location, p.location), p)
        for p in postings
    ]
    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best = scored[0]
    if best_score < _TITLE_MATCH_THRESHOLD:
        return None
    # Ambiguous when a runner-up ties the winner within epsilon — the title
    # match landed on a near-duplicate (common when the scraper dropped a
    # discriminator like "(GO)" from the role).
    ambiguous = any(
        p.url != best.url and score >= best_score - _AMBIGUITY_EPS for score, p in scored[1:]
    )
    return ResolvedApply(
        kind=best.kind,
        apply_url=best.url,
        ats_org=best.org,
        description_html=best.description_html,
        description_text=best.description_text,
        posting_title=best.title,
        via="ats_discovery",
        ambiguous=ambiguous,
    )


async def _fetch_guest_detail(job: Job):
    """Fetch + parse the LinkedIn guest job-detail page (offsite marker + slug + JD)."""
    from services import linkedin_resolver

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
    from services import linkedin_resolver

    guest = await _fetch_guest_detail(job)
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
    discovered = await discover_ats_posting(
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
        discovered = await discover_ats_posting(
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


def apply_resolution(job: Job, resolved: ResolvedApply) -> None:
    """Stamp resolution onto the Job row (caller flushes/commits)."""
    job.apply_url = resolved.apply_url
    job.apply_kind = resolved.kind
    job.apply_resolved_at = datetime.now(UTC)
    job.apply_resolved_via = resolved.via
    board = _KIND_TO_BOARD.get(resolved.kind)
    if board is not None and job.board != board:
        job.board = board
    if resolved.ats_org:
        job.raw_meta = {**(job.raw_meta or {}), "ats_org": resolved.ats_org}
    job.updated_at = datetime.now(UTC)


async def resolve_pending(
    session: AsyncSession,
    *,
    batch_size: int = 12,
    jitter: tuple[float, float] = (2.0, 5.0),
) -> int:
    """Cron sweep: resolve jobs never attempted (`apply_kind IS NULL`).

    Newest first — fresh discoveries are the ones the operator is swiping.
    Jittered sleeps keep the LinkedIn guest endpoint + board APIs polite.
    Returns the number of jobs resolved to a definite kind (not unknown).
    """
    stmt = (
        select(Job)
        .where(Job.apply_kind.is_(None), Job.deleted_at.is_(None))
        .order_by(Job.found_at.desc())
        .limit(batch_size)
    )
    jobs = (await session.exec(stmt)).all()
    if not jobs:
        return 0

    # Authenticated LinkedIn fallback — only when a session is configured, and
    # budgeted so one sweep never opens a long train of authenticated tabs.
    from services import linkedin_resolver

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
            resolved = await resolve_job(job, _cache=cache, auth=auth)
        except Exception as exc:  # noqa: BLE001 — sweep must not die on one job
            log.warning("apply-site resolution failed for job %s: %s", job.id, exc)
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


__all__ = [
    "APPLY_KIND_LABELS",
    "ResolvedApply",
    "apply_resolution",
    "classify_apply_url",
    "discover_ats_posting",
    "resolve_job",
    "resolve_pending",
    "slug_candidates",
    "title_match_score",
]
