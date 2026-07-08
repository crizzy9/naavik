"""Applications package — draft lifecycle, submission, status state-machine,
queries, auto-apply, engagement, export.

Plan 91 Phase 4.2 decomposed the former `services/application_service.py`
god-module (2216 LOC) into
`{common,state,queries,drafts,submission,auto_apply,email_suggestions,
engagement,export}.py`; plan 92 retired the facade and made this `__init__`
the one public surface:

- routes/services import `from services import applications` and call
  `applications.get_application(...)`,
- the conftest attribute shims land on this package module object, and
- `patch("services.applications.X")` targets — including the `ats_dispatch`
  alias — intercept, because the submodules route internal cross-seam calls
  back through this package at call time (`svc()` in `common.py`).

Per BACKEND.md § K + plan 10 § C.3 + DATA_MODEL.md § E.
"""

from __future__ import annotations

from services.applications.auto_apply import (
    AutoApplyResult,
    auto_apply_phase,
    drain_auto_apply_queue,
    pause_auto_apply_for_job,
    process_auto_apply_queue,
)
from services.applications.auto_apply import _hand_to_user as _hand_to_user
from services.applications.auto_apply import _stamp_auto_apply as _stamp_auto_apply
from services.applications.auto_apply import (
    _stamp_auto_apply_artifacts as _stamp_auto_apply_artifacts,
)
from services.applications.common import (
    ApplicationServiceError,
    IllegalStateTransition,
    ValidationError,
)
from services.applications.common import _emit_event as _emit_event
from services.applications.drafts import (
    cleanup_stale_drafts,
    create_manual,
    discard_draft,
    get_or_create_draft,
    queue_auto_apply,
    record_draft_failure,
    record_screener_answer,
    resync_draft_apply_target,
)
from services.applications.email_suggestions import (
    apply_email_suggestion,
    dismiss_email_suggestion,
)
from services.applications.engagement import (
    _roll_up_referral_state as _roll_up_referral_state,
)
from services.applications.engagement import (
    compute_outreach_engagement,
)
from services.applications.export import _defang_csv_cell as _defang_csv_cell
from services.applications.export import (
    list_for_export,
)
from services.applications.pins import (
    PinError,
    auto_transition_allowed,
    clear_pin,
    get_status_pin,
)
from services.applications.queries import (
    aggregate_submission_failures,
    count_applied_since,
    count_unreviewed_required_screeners,
    get_application,
    get_application_for_job,
    get_latest_cover_sections,
    get_screener_answer,
    latest_documents,
    list_applications,
    list_by_status,
    list_closed,
    list_documents_for,
    list_drafts,
    list_events_for,
    list_in_followup,
    list_screener_answers_for,
    list_visible_in_tracking,
    stuck_drafts,
    update_cover_section,
)
from services.applications.rounds import (
    RoundError,
    complete_past_due_rounds,
    create_planned_rounds,
    derive_stage_from_rounds,
    list_rounds,
    resequence_rounds,
    round_chip,
    round_kind_from_title,
    set_round_state,
    upsert_round,
)
from services.applications.staleness import (
    QuietApplication,
    StalenessError,
    list_going_quiet,
    mark_ghosted,
)
from services.applications.staleness import snooze as snooze_staleness
from services.applications.staleness import sweep as staleness_sweep
from services.applications.state import _FORWARD_FROM as _FORWARD_FROM
from services.applications.state import (
    BULK_MAX_IDS,
    bulk_archive,
    bulk_update_status,
    create_tracked_application,
    update_status,
)
from services.applications.state import _is_forward_transition as _is_forward_transition
from services.applications.submission import _build_bundle as _build_bundle
from services.applications.submission import _default_notify_fn as _default_notify_fn
from services.applications.submission import (
    _enforce_sponsorship_gate as _enforce_sponsorship_gate,
)
from services.applications.submission import (
    _persist_reusable_screener_answers as _persist_reusable_screener_answers,
)
from services.applications.submission import _record_failure as _record_failure
from services.applications.submission import _record_success as _record_success
from services.applications.submission import (
    _unreviewed_required_screener_count as _unreviewed_required_screener_count,
)
from services.applications.submission import (
    retry_failed,
    submit_draft,
    validate_submittable,
)

# Patched seam (8 tests patch `services.applications.ats_dispatch`);
# `submission.submit_draft` calls it through this facade.
from services.ats import dispatch as ats_dispatch

__all__ = [
    "BULK_MAX_IDS",
    "ApplicationServiceError",
    "AutoApplyResult",
    "IllegalStateTransition",
    "ValidationError",
    "aggregate_submission_failures",
    "apply_email_suggestion",
    "ats_dispatch",
    "auto_apply_phase",
    "bulk_archive",
    "bulk_update_status",
    "RoundError",
    "PinError",
    "auto_transition_allowed",
    "clear_pin",
    "get_status_pin",
    "QuietApplication",
    "StalenessError",
    "list_going_quiet",
    "mark_ghosted",
    "snooze_staleness",
    "staleness_sweep",
    "complete_past_due_rounds",
    "create_planned_rounds",
    "create_tracked_application",
    "derive_stage_from_rounds",
    "list_rounds",
    "resequence_rounds",
    "round_chip",
    "round_kind_from_title",
    "set_round_state",
    "upsert_round",
    "cleanup_stale_drafts",
    "compute_outreach_engagement",
    "count_applied_since",
    "count_unreviewed_required_screeners",
    "create_manual",
    "discard_draft",
    "dismiss_email_suggestion",
    "drain_auto_apply_queue",
    "get_application",
    "get_application_for_job",
    "get_latest_cover_sections",
    "get_or_create_draft",
    "get_screener_answer",
    "latest_documents",
    "list_applications",
    "list_by_status",
    "list_closed",
    "list_documents_for",
    "list_drafts",
    "list_events_for",
    "list_for_export",
    "list_in_followup",
    "list_screener_answers_for",
    "list_visible_in_tracking",
    "pause_auto_apply_for_job",
    "process_auto_apply_queue",
    "queue_auto_apply",
    "record_draft_failure",
    "record_screener_answer",
    "resync_draft_apply_target",
    "retry_failed",
    "stuck_drafts",
    "submit_draft",
    "update_cover_section",
    "update_status",
    "validate_submittable",
]
