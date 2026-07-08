"""Email package — IMAP sync, LLM classification, application inference,
credentials, status mapping, ICS calendar sync, and the thread read API.

Plan 92 Phase B1 grouped the former flat modules `email_service` /
`email_sync` / `email_classifier` / `email_credentials` /
`email_application_inference` / `email_status_mapper` / `calendar_sync` /
`imap_host_guard` into this package.

Seam tiers:

- Package surface (this `__init__`): the thread read API (conftest shims
  land here — routes read `email.list_threads(...)` at call time) and the
  route-called sync seams (`sync_account` / `test_imap_connection` /
  `sync_all_accounts`) that tests patch as `services.email.X`.
- Module tier (import the submodule): `classifier`, `inference`,
  `credentials`, `status_mapper`, `calendar_sync`, `imap_host_guard` and
  sync internals — patch as `services.email.<mod>.X`; intra-module reads
  intercept without any routing.
"""

from __future__ import annotations

from services.email.service import (
    PendingSuggestion,
    get_thread,
    list_accounts,
    list_pending_suggestions,
    list_threads,
    list_threads_for_application,
    recent_signals,
)
from services.email.sync import (
    SyncResult,
    sync_account,
    sync_all_accounts,
    test_imap_connection,
)

__all__ = [
    "PendingSuggestion",
    "SyncResult",
    "get_thread",
    "list_accounts",
    "list_pending_suggestions",
    "list_threads",
    "list_threads_for_application",
    "recent_signals",
    "sync_account",
    "sync_all_accounts",
    "test_imap_connection",
]
