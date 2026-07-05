"""LinkedIn resolver — facade over `services/resolution/linkedin.py`
(plan 91 4.5).

Re-exports every name (public + the private helpers tests touch) so all
importers and `patch.object(linkedin_resolver, ...)` seams resolve
unchanged; the moved module routes its internal session-health calls back
through this facade. `_AUTH_LOCK` stays single-instance: the implementation
module owns it and this facade re-exports the bound name (cross-cutting
rule §5) — the serialized-Patchright contract from
[[reference-linkedin-auth-resolver]] is untouched.

Facade teardown happens in Phase 8, after importers are flipped.
"""

from __future__ import annotations

# Tests monkeypatch lr.settings.data_dir — the shared config singleton.
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
