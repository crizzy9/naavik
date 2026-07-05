"""Resolution package — apply-site resolution pipeline + LinkedIn auth tiers.

Plan 91 Phase 4.5 decomposed `services/apply_site_resolver.py` +
`services/linkedin_resolver.py` into
`{common,url_rules,board_probe,pipeline,linkedin}.py`; plan 92 retired the
facades and made this `__init__` the one public surface. Seams tests
`patch.object` on this package intercept internal calls because the
submodules route cross-seam calls back through it at call time
(`svc()` / `_li()`).

`_AUTH_LOCK` stays single-instance: `linkedin.py` owns it and this package
re-exports the bound name (plan 91 cross-cutting rule §5) — the
serialized-Patchright contract from [[reference-linkedin-auth-resolver]]
is untouched.
"""

from __future__ import annotations

# Tests `patch.object(resolver.asyncio, "sleep")` — the stdlib module object,
# so mutations are visible to the moved pipeline code too.
import asyncio as asyncio

# Tests monkeypatch `lr.settings.data_dir` — the shared config singleton.
from config import settings as settings

# Patched seam: tests `patch.object(resolver, "is_safe_destination")`.
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
from services.resolution.linkedin import _AUTH_LOCK as _AUTH_LOCK
from services.resolution.linkedin import (
    GUEST_OFFSITE_MARKER,
    AuthContext,
    AuthFetch,
    GuestDetail,
    VoyagerApply,
    auth_available,
    cookie_payload,
    extract_apply_from_voyager,
    mark_health_alerted,
    parse_guest_detail,
    profile_dir,
    read_session_health,
    record_session_health,
    resolve_via_auth,
    resolved_from_fetch,
)
from services.resolution.linkedin import (
    _chromium_executable as _chromium_executable,
)
from services.resolution.linkedin import _health_path as _health_path
from services.resolution.linkedin import _open_and_fetch as _open_and_fetch
from services.resolution.linkedin import _write_health as _write_health
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
    "GUEST_OFFSITE_MARKER",
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
    "AuthContext",
    "AuthFetch",
    "GuestDetail",
    "VoyagerApply",
    "auth_available",
    "cookie_payload",
    "extract_apply_from_voyager",
    "mark_health_alerted",
    "parse_guest_detail",
    "profile_dir",
    "read_session_health",
    "record_session_health",
    "resolve_via_auth",
    "resolved_from_fetch",
]
