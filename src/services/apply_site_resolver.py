"""Apply-site resolver — facade over `services/resolution/` (plan 91 4.5).

The former 905-LOC module is decomposed into
`services/resolution/{common,url_rules,board_probe,pipeline}.py` (LinkedIn
auth machinery lives in `resolution/linkedin.py` behind the
`services.linkedin_resolver` facade). This module re-exports every name —
public API, the private probe/postings helpers tests `patch.object` on this
module, and the `is_safe_destination` / retry-ladder constants — so all
importers and seams resolve unchanged. The submodules route internal calls
to patched names back through this facade.

The resolver↔linkedin lazy-import cycle is dissolved inside the package
(`resolution/linkedin.py` imports `resolution/url_rules.py` directly).

Facade teardown happens in Phase 8, after importers are flipped.
"""

from __future__ import annotations

# Tests patch.object(resolver.asyncio, "sleep") — the stdlib module object,
# so mutations are visible to the moved pipeline code too.
import asyncio as asyncio

# Patched seam: tests patch.object(resolver, "is_safe_destination").
from scraper.url_guard import is_safe_destination
from services.resolution.board_probe import _ashby_postings as _ashby_postings
from services.resolution.board_probe import _fetch as _fetch
from services.resolution.board_probe import _fetch_slug_boards as _fetch_slug_boards
from services.resolution.board_probe import (
    _greenhouse_postings as _greenhouse_postings,
)
from services.resolution.board_probe import _lever_postings as _lever_postings
from services.resolution.board_probe import _redirect_probe as _redirect_probe
from services.resolution.board_probe import _sanitize_slug as _sanitize_slug
from services.resolution.board_probe import (
    discover_ats_posting,
    normalize_apply_url,
)
from services.resolution.common import _AMBIGUITY_EPS as _AMBIGUITY_EPS
from services.resolution.common import _FETCH_TIMEOUT as _FETCH_TIMEOUT
from services.resolution.common import _KIND_TO_BOARD as _KIND_TO_BOARD
from services.resolution.common import (
    _LINKEDIN_DETAIL_BASE as _LINKEDIN_DETAIL_BASE,
)
from services.resolution.common import _MAX_REDIRECTS as _MAX_REDIRECTS
from services.resolution.common import _RETRY_BACKOFF as _RETRY_BACKOFF
from services.resolution.common import _RETRY_RESERVE as _RETRY_RESERVE
from services.resolution.common import (
    _TITLE_MATCH_THRESHOLD as _TITLE_MATCH_THRESHOLD,
)
from services.resolution.common import (
    APPLY_KIND_LABELS,
    MAX_RESOLVE_ATTEMPTS,
)
from services.resolution.pipeline import _fetch_guest_detail as _fetch_guest_detail
from services.resolution.pipeline import _resolve_linkedin as _resolve_linkedin
from services.resolution.pipeline import (
    _schedule_or_settle as _schedule_or_settle,
)
from services.resolution.pipeline import (
    apply_resolution,
    note_failed_attempt,
    resolve_job,
    resolve_pending,
    resolver_stats,
)
from services.resolution.url_rules import (
    ResolvedApply,
    ats_org_from_url,
    classify_apply_url,
    slug_candidates,
    title_match_score,
    unwrap_tracking_url,
)
from services.resolution.url_rules import _BoardPosting as _BoardPosting
from services.resolution.url_rules import _location_bonus as _location_bonus
from services.resolution.url_rules import _normalize_title as _normalize_title

__all__ = [
    "APPLY_KIND_LABELS",
    "MAX_RESOLVE_ATTEMPTS",
    "ResolvedApply",
    "apply_resolution",
    "ats_org_from_url",
    "classify_apply_url",
    "discover_ats_posting",
    "is_safe_destination",
    "normalize_apply_url",
    "note_failed_attempt",
    "resolve_job",
    "resolve_pending",
    "resolver_stats",
    "slug_candidates",
    "title_match_score",
    "unwrap_tracking_url",
]
