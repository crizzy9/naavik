"""Notifications — facade over `services/notify/` (plan 91 4.6).

The former module is decomposed into `services/notify/{channels,events}.py`.
This module re-exports every name (event vocabulary, senders, composite
emitters, and the private renderer/env seams ten tests patch —
`_telegram_token`, `_telegram_chat_id`, `_discord_url`,
`_send_*_scrape_run`) so all importers and `patch("services.notifications.X")`
targets resolve unchanged. The submodules route internal cross-seam calls
back through this facade.

In-app toasts are NOT this module's job (the queue path was deleted in
plan 91 2.3): live toasts ride the `HX-Trigger: {"showToast": ...}` response
header wired in `base.js`.

Facade teardown happens in Phase 8, after importers are flipped.
"""

from __future__ import annotations

from services.notify.channels import (
    _discord_url as _discord_url,
)
from services.notify.channels import (
    _send_discord_scrape_run as _send_discord_scrape_run,
)
from services.notify.channels import (
    _send_telegram_scrape_run as _send_telegram_scrape_run,
)
from services.notify.channels import (
    _telegram_chat_id as _telegram_chat_id,
)
from services.notify.channels import (
    _telegram_token as _telegram_token,
)
from services.notify.channels import (
    notify_admin_error,
    send_discord,
    send_telegram,
    send_test_message,
)
from services.notify.events import (
    _SCRAPE_RUN_TOP_N as _SCRAPE_RUN_TOP_N,
)
from services.notify.events import (
    EVENT_APPLICATION_SENT,
    EVENT_AUTO_APPLY_FAILED,
    EVENT_INTERVIEW_SCHEDULED,
    EVENT_NEW_HIGH_SCORE,
    EVENT_OFFER_RECEIVED,
    EVENT_REJECTION,
    EVENT_SCRAPE_RUN_NEW_JOBS,
    notify_application_submitted,
    notify_new_high_score,
    notify_priority_email,
    notify_scrape_run_summary,
)
from services.notify.events import (
    _embed_for_event as _embed_for_event,
)
from services.notify.events import (
    _embed_for_scrape_run as _embed_for_scrape_run,
)
from services.notify.events import (
    _is_event_enabled as _is_event_enabled,
)
from services.notify.events import (
    _telegram_text_for_event as _telegram_text_for_event,
)
from services.notify.events import (
    _telegram_text_for_scrape_run as _telegram_text_for_scrape_run,
)

__all__ = [
    "EVENT_APPLICATION_SENT",
    "EVENT_AUTO_APPLY_FAILED",
    "EVENT_INTERVIEW_SCHEDULED",
    "EVENT_NEW_HIGH_SCORE",
    "EVENT_OFFER_RECEIVED",
    "EVENT_REJECTION",
    "EVENT_SCRAPE_RUN_NEW_JOBS",
    "notify_admin_error",
    "notify_application_submitted",
    "notify_new_high_score",
    "notify_priority_email",
    "notify_scrape_run_summary",
    "send_discord",
    "send_telegram",
    "send_test_message",
]
