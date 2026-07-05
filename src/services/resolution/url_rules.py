"""URL classification, tracking-unwrap, slug + title-match heuristics.

Split out of services/apply_site_resolver.py in plan 91 Phase 4.5;
behaviour unchanged. Internal calls to patched seams route through `svc()`
(the services.apply_site_resolver facade) so test interception keeps
working; LinkedIn-auth calls stay lazy through the linkedin_resolver
facade for the same reason.
"""

from __future__ import annotations

import difflib
import logging
import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, unquote, urlparse

from services.resolution.common import (
    _ATS_HOST_PATTERNS,
    _COMPANY_NOISE,
)

log = logging.getLogger(__name__)


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
    # "linkedin_auth", "board_trust", "manual") vs guessed ("ats_discovery") vs
    # "unresolved" (retry-scheduled) / "exhausted" (retries spent).
    via: str | None = None
    # When normalization rewrote the URL (tracking wrapper unwrapped, redirect
    # chain followed), the pre-normalization URL — persisted to
    # raw_meta["apply_url_original"] for provenance.
    original_apply_url: str | None = None
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


# The greenhouse/lever/ashby org slug sits in the URL path.
_ATS_ORG_RE = re.compile(r"(?:greenhouse\.io|lever\.co|ashbyhq\.com)/([^/?#]+)")


def ats_org_from_url(url: str | None, kind: str | None) -> str | None:
    """Org slug from a Greenhouse/Lever/Ashby posting URL; None otherwise."""
    if not url or kind not in ("greenhouse", "lever", "ashby"):
        return None
    m = _ATS_ORG_RE.search(url)
    return m.group(1) if m else None


# Query-param names tracking wrappers stash the real destination in
# (appcast/jibe/LinkedIn externalApply style `?url=…`). Only values that are
# themselves complete http(s) URLs count — a plain path never rewrites.
_WRAPPER_QUERY_KEYS = frozenset(
    {
        "url",
        "u",
        "redirect",
        "redirect_url",
        "redirect_uri",
        "dest",
        "destination",
        "target",
        "joburl",
        "job_url",
    }
)


def unwrap_tracking_url(url: str, *, max_depth: int = 3) -> str:
    """Peel tracking-wrapper layers whose query carries the real URL. Pure."""
    current = url
    for _ in range(max_depth):
        try:
            parsed = urlparse(current)
        except ValueError:
            return current
        inner: str | None = None
        for key, value in parse_qsl(parsed.query):
            if key.lower() not in _WRAPPER_QUERY_KEYS:
                continue
            candidate = value if value.startswith(("http://", "https://")) else unquote(value)
            if candidate.startswith(("http://", "https://")):
                inner = candidate
                break
        if inner is None or inner == current:
            return current
        current = inner
    return current


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
