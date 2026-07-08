"""Scheduling package — plan 96 slice 96f (owner decisions #5, #6).

Detect → suggest slots → draft in the owner's voice; **the owner sends**.
No SMTP, no send scopes, no calendar writes — pinned by the static no-send
guard test. The package __init__ is the ONE public/patch surface (plans
92-93 seam discipline):

- `detect` tier: `action_needed_post_check` (the classifier's deterministic
  gate) + `list_needs_scheduling` (the Tracking strip's rows).
- `slots` tier: the pure free-slot engine (`free_slots`, `parse_window`,
  `format_slot`).
- `draft` tier: `build_scheduling_draft` (slots + owner-voice reply +
  Gmail compose deep-link; persists only a NOTE_ADDED AppEvent).

`Settings.scheduling_autonomy` naming stays reserved for a future consented
send rung — deliberately unbuilt (§ 5.6).
"""

from __future__ import annotations

from services.scheduling.detect import (
    ACTION_LABELS,
    ACTION_NEEDED_VOCAB,
    NeedsScheduling,
    action_needed_post_check,
    list_needs_scheduling,
)
from services.scheduling.draft import (
    SchedulingDraft,
    SchedulingError,
    build_scheduling_draft,
    busy_intervals,
    gmail_compose_url,
    resolve_timezone,
    suggest_slots,
)
from services.scheduling.slots import (
    DEFAULT_WINDOW,
    Slot,
    format_slot,
    free_slots,
    parse_window,
)

__all__ = [
    "ACTION_LABELS",
    "ACTION_NEEDED_VOCAB",
    "DEFAULT_WINDOW",
    "NeedsScheduling",
    "SchedulingDraft",
    "SchedulingError",
    "Slot",
    "action_needed_post_check",
    "build_scheduling_draft",
    "busy_intervals",
    "format_slot",
    "free_slots",
    "gmail_compose_url",
    "list_needs_scheduling",
    "parse_window",
    "resolve_timezone",
    "suggest_slots",
]
