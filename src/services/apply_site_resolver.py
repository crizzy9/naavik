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

_OFFSITE_MARKER = "apply-link-offsite"
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


async def discover_ats_posting(
    *,
    company: str,
    role: str,
    location: str | None = None,
    _cache: dict[str, list[_BoardPosting]] | None = None,
) -> ResolvedApply | None:
    """Probe public Greenhouse/Lever/Ashby board APIs for this company+role.

    Strict title matching (>= 0.72 similarity or containment) keeps us from
    attaching the WRONG posting — no hit beats a guessed hit. `_cache` lets a
    sweep reuse board fetches across same-company jobs.
    """
    postings: list[_BoardPosting] = []
    cache_key = (company or "").strip().lower()
    if _cache is not None and cache_key in _cache:
        postings = _cache[cache_key]
    else:
        for slug in slug_candidates(company):
            for fetcher in (_greenhouse_postings, _lever_postings, _ashby_postings):
                try:
                    postings = await fetcher(slug)
                except (httpx.HTTPError, OSError) as exc:
                    log.info("ATS discovery fetch failed for %s: %s", slug, exc)
                    postings = []
                if postings:
                    break
            if postings:
                break
        if _cache is not None:
            _cache[cache_key] = postings
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
    return ResolvedApply(
        kind=best.kind,
        apply_url=best.url,
        ats_org=best.org,
        description_html=best.description_html,
        description_text=best.description_text,
        posting_title=best.title,
    )


async def _linkedin_is_offsite(job: Job) -> bool | None:
    """True = external apply, False = native Easy Apply, None = can't tell."""
    detail_url = (job.raw_meta or {}).get("detail_endpoint") or (
        f"{_LINKEDIN_DETAIL_BASE}{job.external_id}"
    )
    try:
        resp = await _fetch(detail_url, accept="text/html")
    except (httpx.HTTPError, OSError) as exc:
        log.info("linkedin offsite probe failed for job %s: %s", job.id, exc)
        return None
    if resp is None or resp.status_code != 200 or not resp.text:
        return None
    return _OFFSITE_MARKER in resp.text


async def resolve_job(
    job: Job,
    *,
    _cache: dict[str, list[_BoardPosting]] | None = None,
) -> ResolvedApply:
    """Resolve one job's real application target. Pure of session writes."""
    # 1. The listing URL itself already lives on an ATS host (direct ATS
    #    scrapes, some MANUAL pastes, email receipts with posting links).
    direct = classify_apply_url(job.url)
    if direct is not None:
        return ResolvedApply(kind=direct, apply_url=job.url)

    posting_url = (job.raw_meta or {}).get("posting_url")
    direct = classify_apply_url(posting_url)
    if direct is not None:
        return ResolvedApply(kind=direct, apply_url=posting_url)

    if job.source == JobSource.LINKEDIN:
        offsite = await _linkedin_is_offsite(job)
        if offsite is False:
            return ResolvedApply(kind="easy_apply", apply_url=job.url)
        discovered = await discover_ats_posting(
            company=job.company, role=job.role, location=job.location, _cache=_cache
        )
        if discovered is not None:
            return discovered
        # Known-external but target unresolvable (LinkedIn gates the URL).
        return ResolvedApply(kind="external" if offsite else "unknown", apply_url=None)

    if job.source in (JobSource.INDEED, JobSource.EMAIL, JobSource.MANUAL):
        discovered = await discover_ats_posting(
            company=job.company, role=job.role, location=job.location, _cache=_cache
        )
        if discovered is not None:
            return discovered
        return ResolvedApply(kind="unknown", apply_url=None)

    # Direct ATS scrape whose URL didn't pattern-match (rare) — trust board.
    if job.board in (
        ApplicationBoard.GREENHOUSE,
        ApplicationBoard.LEVER,
        ApplicationBoard.ASHBY,
        ApplicationBoard.WORKDAY,
    ):
        return ResolvedApply(kind=job.board.value, apply_url=job.url)
    return ResolvedApply(kind="unknown", apply_url=None)


def apply_resolution(job: Job, resolved: ResolvedApply) -> None:
    """Stamp resolution onto the Job row (caller flushes/commits)."""
    job.apply_url = resolved.apply_url
    job.apply_kind = resolved.kind
    job.apply_resolved_at = datetime.now(UTC)
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

    cache: dict[str, list[_BoardPosting]] = {}
    definite = 0
    for i, job in enumerate(jobs):
        if i > 0:
            await asyncio.sleep(random.uniform(*jitter))
        try:
            resolved = await resolve_job(job, _cache=cache)
        except Exception as exc:  # noqa: BLE001 — sweep must not die on one job
            log.warning("apply-site resolution failed for job %s: %s", job.id, exc)
            continue
        apply_resolution(job, resolved)
        # Discovery already carried the canonical JD — enrich for free while
        # we hold it (thin Indeed/email descriptions get the real posting).
        if resolved.description_html or resolved.description_text:
            from services import jd_enrichment

            jd_enrichment.maybe_apply_discovered_description(job, resolved)
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
