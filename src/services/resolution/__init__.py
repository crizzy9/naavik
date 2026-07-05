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

# Tests monkeypatch `lr.settings.data_dir` — the shared config singleton.
from config import settings as settings
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

__all__ = [
    "GUEST_OFFSITE_MARKER",
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
