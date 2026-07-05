"""Network probes — redirect walk, SSRF-guarded fetch, board-API postings, ATS discovery.

Split out of the former services/apply_site_resolver.py in plan 91 Phase 4.5;
behaviour unchanged. Internal calls to patched seams route through `svc()`
(the services.resolution package surface) so test interception keeps
working; LinkedIn-auth calls stay lazy through the linkedin_resolver
facade for the same reason.
"""

from __future__ import annotations

import logging
import re

import httpx

from scraper.user_agents import pick_user_agent
from services.resolution.common import (
    _AMBIGUITY_EPS,
    _FETCH_TIMEOUT,
    _MAX_REDIRECTS,
    _TITLE_MATCH_THRESHOLD,
    svc,
)
from services.resolution.url_rules import (
    ResolvedApply,
    _BoardPosting,
    _location_bonus,
    classify_apply_url,
    slug_candidates,
    title_match_score,
    unwrap_tracking_url,
)

log = logging.getLogger(__name__)


async def _redirect_probe(
    client: httpx.AsyncClient, url: str, headers: dict[str, str]
) -> httpx.Response | None:
    """HEAD, falling back to a body-less GET — we only want status + Location."""
    try:
        resp = await client.head(url, headers=headers)
        if resp.status_code not in (405, 501):
            return resp
    except (httpx.HTTPError, OSError):
        pass
    try:
        req = client.build_request("GET", url, headers=headers)
        resp = await client.send(req, stream=True)
        await resp.aclose()
        return resp
    except (httpx.HTTPError, OSError):
        return None


async def normalize_apply_url(
    url: str, *, max_hops: int = 5, timeout: float = 8.0
) -> tuple[str, str | None]:
    """(final_url, kind|None) — unwrap wrappers, follow redirects, classify.

    Tier B's `companyApplyUrl` (and manual pastes) can be a tracking wrapper or
    a careers page that 302s onto the real ATS (`careers.x.com` →
    `x.wdX.myworkdayjobs.com`). Zero network when unwrapping alone classifies;
    otherwise each hop is SSRF-guarded and the walk early-exits the moment any
    hop's URL classifies. Network failure degrades to the best-known URL —
    never raises.
    """
    current = unwrap_tracking_url(url)
    kind = classify_apply_url(current)
    if kind is not None:
        return current, kind
    headers = {"User-Agent": pick_user_agent()}
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            for _ in range(max_hops):
                safe, reason = svc().is_safe_destination(current)
                if not safe:
                    log.info("apply-url normalize blocked (%s): %s", reason, current[:120])
                    break
                resp = await svc()._redirect_probe(client, current, headers)
                if resp is None or resp.status_code not in (301, 302, 303, 307, 308):
                    break
                location = resp.headers.get("location")
                if not location:
                    break
                current = unwrap_tracking_url(str(httpx.URL(current).join(location)))
                kind = classify_apply_url(current)
                if kind is not None:
                    return current, kind
    except (httpx.HTTPError, OSError) as exc:
        log.info("apply-url normalize failed for %s: %s", url[:120], exc)
    return current, classify_apply_url(current)


async def _fetch(url: str, *, accept: str = "application/json") -> httpx.Response | None:
    """SSRF-guarded GET with manual redirect re-checking (calendar_sync pattern)."""
    current = url
    headers = {"User-Agent": pick_user_agent(), "Accept": accept}
    async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT, follow_redirects=False) as client:
        for _ in range(_MAX_REDIRECTS + 1):
            safe, reason = svc().is_safe_destination(current)
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
    for fetcher in (svc()._greenhouse_postings, svc()._lever_postings, svc()._ashby_postings):
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
