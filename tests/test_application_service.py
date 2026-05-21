"""Wave 6 — application_service tests.

Per plan 10 § E. Coverage:
- get_or_create_draft (eager / lazy gates)
- submit_draft success + persistent failure (stuck-queue surface)
- discard_draft
- process_auto_apply_queue
- validate_submittable
- forward-only state-transition enforcement
- service-layer computed state — referral rollup, outreach engagement,
  Job.queue_state flip on submit
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from services import application_service as svc
from services.application_service import (
    IllegalStateTransition,
    ValidationError,
    _is_forward_transition,
    _roll_up_referral_state,
    compute_outreach_engagement,
    discard_draft,
    get_or_create_draft,
    process_auto_apply_queue,
    submit_draft,
    update_status,
    validate_submittable,
)
from services.ats.base import (
    FAILURE_AUTH_REQUIRED,
    FAILURE_RATE_LIMIT,
    SubmissionResult,
)

# ── In-memory fakes — minimal stand-ins for SQLModel rows ────────────


class _FakeSession:
    """Tracks add()/flush()/exec() calls; serves canned exec results."""

    def __init__(self) -> None:
        self.added: list = []
        self.deleted: list = []
        self.exec_queue: list = []
        self.flush_count = 0

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flush_count += 1

    async def delete(self, obj):
        self.deleted.append(obj)

    async def exec(self, _stmt):
        if not self.exec_queue:
            return SimpleNamespace(one_or_none=lambda: None, all=lambda: [], one=lambda: 0)
        return self.exec_queue.pop(0)


def _exec_one(value):
    return SimpleNamespace(
        one_or_none=lambda: value, all=lambda: [value] if value else [], one=lambda: value
    )


def _exec_all(values):
    return SimpleNamespace(
        one_or_none=lambda: values[0] if values else None,
        all=lambda: values,
        one=lambda: len(values),
    )


def _exec_count(count):
    return SimpleNamespace(one=lambda: count, all=lambda: [count], one_or_none=lambda: count)


def _make_settings(**kw):
    base = {
        "user_id": 1,
        "eager_review_generation": True,
        "auto_apply_enabled": True,
        "auto_apply_score_threshold": 0.7,
        "auto_apply_daily_cap": None,
        "daily_llm_cost_cap_usd": None,
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _make_job(jid: int = 100, **kw):
    from models import ApplicationBoard, JobQueueState

    base = {
        "id": jid,
        "company": "Stripe",
        "role": "Senior Backend Engineer",
        "team": None,
        "location": "Remote",
        "salary_min": 180000,
        "salary_max": 240000,
        "equity_pct": None,
        "url": "https://boards.greenhouse.io/stripe/jobs/123456",
        "url_type": "https",
        "board": ApplicationBoard.GREENHOUSE,
        "queue_state": JobQueueState.UNSWIPED,
        "description": "Build payment infra at scale",
        "description_html": None,
        "skills_required": ["python", "go"],
        "visa_restrictions": None,
        "updated_at": datetime.now(UTC),
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _make_app(aid: int = 1, **kw):
    from models import ApplicationBoard, ApplicationStatus, DocsState, RecruiterState, ReferralState

    base = {
        "id": aid,
        "user_id": 1,
        "job_id": 100,
        "company": "Stripe",
        "role": "Senior Backend Engineer",
        "team": None,
        "location": "Remote",
        "salary_min": None,
        "salary_max": None,
        "equity_pct": None,
        "applied_at": None,
        "board": ApplicationBoard.GREENHOUSE,
        "external_url": "https://boards.greenhouse.io/stripe/jobs/123456",
        "status": ApplicationStatus.DRAFT,
        "closed_reason": None,
        "docs_state": DocsState.READY,
        "referral_state": ReferralState.NONE,
        "recruiter_state": RecruiterState.NONE,
        "submission_artifacts": None,
        "notes": None,
        "deleted_at": None,
        "updated_at": datetime.now(UTC),
    }
    base.update(kw)
    return SimpleNamespace(**base)


# ── Forward-transition rules ─────────────────────────────────────────


def test_forward_transition_rules():
    from models import ApplicationStatus as S

    assert _is_forward_transition(S.DRAFT, S.APPLIED) is True
    assert _is_forward_transition(S.APPLIED, S.RECRUITER_SCREEN) is True
    assert _is_forward_transition(S.RECRUITER_SCREEN, S.APPLIED) is False
    assert _is_forward_transition(S.OFFER, S.CLOSED) is True
    assert _is_forward_transition(S.CLOSED, S.APPLIED) is False
    assert _is_forward_transition(S.DRAFT, S.OFFER) is False


# ── get_or_create_draft ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_or_create_draft_eager_calls_pre_generate():
    settings = _make_settings(eager_review_generation=True)
    job = _make_job()
    session = _FakeSession()
    # exec calls in order: existing app lookup (None), job lookup (job).
    session.exec_queue = [_exec_one(None), _exec_one(job)]

    pre_gen = AsyncMock()
    draft = await get_or_create_draft(
        session, user_id=1, job_id=100, settings=settings, pre_generate_fn=pre_gen
    )
    from models import ApplicationStatus

    assert draft.status == ApplicationStatus.DRAFT
    assert draft.user_id == 1
    assert draft.job_id == 100
    pre_gen.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_or_create_draft_lazy_skips_pre_generate():
    settings = _make_settings(eager_review_generation=False)
    job = _make_job()
    session = _FakeSession()
    session.exec_queue = [_exec_one(None), _exec_one(job)]
    pre_gen = AsyncMock()
    await get_or_create_draft(
        session, user_id=1, job_id=100, settings=settings, pre_generate_fn=pre_gen
    )
    pre_gen.assert_not_called()


@pytest.mark.asyncio
async def test_get_or_create_draft_returns_existing():
    settings = _make_settings()
    existing = _make_app()
    session = _FakeSession()
    session.exec_queue = [_exec_one(existing)]
    out = await get_or_create_draft(
        session, user_id=1, job_id=100, settings=settings, pre_generate_fn=AsyncMock()
    )
    assert out is existing


# ── validate_submittable ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_validate_submittable_rejects_non_draft():
    from models import ApplicationStatus

    a = _make_app(status=ApplicationStatus.APPLIED)
    session = _FakeSession()
    with pytest.raises(ValidationError) as exc:
        await validate_submittable(session, a)
    assert exc.value.code == "not_draft"


@pytest.mark.asyncio
async def test_validate_submittable_rejects_unready_docs():
    from models import DocsState

    a = _make_app(docs_state=DocsState.GENERATING)
    session = _FakeSession()
    with pytest.raises(ValidationError) as exc:
        await validate_submittable(session, a)
    assert exc.value.code == "docs_not_ready"


@pytest.mark.asyncio
async def test_validate_submittable_blocks_unreviewed_screeners():
    a = _make_app()
    session = _FakeSession()
    session.exec_queue = [_exec_count(2)]
    with pytest.raises(ValidationError) as exc:
        await validate_submittable(session, a)
    assert exc.value.code == "screeners_unreviewed"


@pytest.mark.asyncio
async def test_validate_submittable_passes_when_clean():
    a = _make_app()
    session = _FakeSession()
    session.exec_queue = [_exec_count(0)]
    # No raise = pass. Sponsorship-gate Profile/Job lookups fall through to
    # default empty-queue → one_or_none=None → gate short-circuits.
    await validate_submittable(session, a)


# ── validate_submittable sponsorship-gate (plan 76 § D.1) ────────────


def _make_profile(*, sponsorship: str = "needed_now"):
    from models import VisaSponsorship

    return SimpleNamespace(
        user_id=1,
        visa_sponsorship_needed=VisaSponsorship(sponsorship),
    )


@pytest.mark.asyncio
async def test_validate_submittable_blocks_no_sponsorship_job():
    """H1B profile (NEEDED_NOW) + US_CITIZEN_ONLY job → ValidationError code=visa_incompatible."""
    from models import VisaRestriction

    a = _make_app()
    profile = _make_profile()
    job = _make_job(visa_restrictions=VisaRestriction.US_CITIZEN_ONLY)
    session = _FakeSession()
    session.exec_queue = [_exec_count(0), _exec_one(profile), _exec_one(job)]

    with pytest.raises(ValidationError) as exc:
        await validate_submittable(session, a)
    assert exc.value.code == "visa_incompatible"


@pytest.mark.asyncio
async def test_validate_submittable_blocks_green_card_job():
    """H1B profile + GREEN_CARD_REQUIRED job → ValidationError code=visa_incompatible."""
    from models import VisaRestriction

    a = _make_app()
    profile = _make_profile()
    job = _make_job(visa_restrictions=VisaRestriction.GREEN_CARD_REQUIRED)
    session = _FakeSession()
    session.exec_queue = [_exec_count(0), _exec_one(profile), _exec_one(job)]

    with pytest.raises(ValidationError) as exc:
        await validate_submittable(session, a)
    assert exc.value.code == "visa_incompatible"


@pytest.mark.asyncio
async def test_validate_submittable_allows_visa_friendly_job():
    """H1B profile + SPONSORSHIP_AVAILABLE job → passes (no raise)."""
    from models import VisaRestriction

    a = _make_app()
    profile = _make_profile()
    job = _make_job(visa_restrictions=VisaRestriction.SPONSORSHIP_AVAILABLE)
    session = _FakeSession()
    session.exec_queue = [_exec_count(0), _exec_one(profile), _exec_one(job)]

    await validate_submittable(session, a)


@pytest.mark.asyncio
async def test_validate_submittable_bypasses_manual_entry():
    """No job_id → sponsorship-gate skipped regardless of profile (manual entries)."""
    a = _make_app(job_id=None)
    session = _FakeSession()
    # Only the screener-count exec runs; gate early-returns on job_id IS NULL.
    session.exec_queue = [_exec_count(0)]

    await validate_submittable(session, a)


# ── submit_draft success + failure paths ────────────────────────────


@pytest.mark.asyncio
async def test_submit_draft_success_flips_state_and_job_queue_state():
    """Happy path — DRAFT → APPLIED + Job.queue_state=APPLIED."""
    from models import ApplicationStatus, JobQueueState

    app_row = _make_app()
    job_row = _make_job()

    session = _FakeSession()
    # exec sequence:
    # 1. get_application(id) → app
    # 2. validate: count(unreviewed) = 0
    # 3. sponsorship-gate: Profile lookup → None (short-circuits gate; plan 76)
    # 4. Settings load (for postmortem LLM provider)
    # 5. _build_bundle: resume → None, cover → None, screeners → []
    # 6. job lookup (post-success flip)
    session.exec_queue = [
        _exec_one(app_row),
        _exec_count(0),
        _exec_one(None),  # sponsorship-gate Profile → None
        _exec_one(None),  # Settings load
        _exec_one(None),  # resume lookup
        _exec_one(None),  # cover lookup
        _exec_all([]),  # screeners
        _exec_one(job_row),  # post-success
    ]

    fake_adapter = SimpleNamespace(
        submit=AsyncMock(return_value=SubmissionResult(ok=True, board_application_id="GH-12345"))
    )
    notify = AsyncMock()

    with patch("services.application_service.ats_dispatch", return_value=fake_adapter):
        out = await submit_draft(session, app_row.id, notify_fn=notify)

    assert out.status == ApplicationStatus.APPLIED
    assert out.applied_at is not None
    assert (out.submission_artifacts or {}).get("board_application_id") == "GH-12345"
    assert job_row.queue_state == JobQueueState.APPLIED
    notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_submit_draft_persistent_failure_keeps_draft_and_writes_last_failure():
    """Auth-required failure → DRAFT stays + submission_artifacts.last_failure.kind='auth_required'."""
    from models import ApplicationStatus

    app_row = _make_app()
    session = _FakeSession()
    session.exec_queue = [
        _exec_one(app_row),  # get_application
        _exec_count(0),  # validate
        _exec_one(None),  # sponsorship-gate Profile → None (plan 76)
        _exec_one(None),  # Settings load
        _exec_one(None),
        _exec_one(None),
        _exec_all([]),
    ]

    fake_adapter = SimpleNamespace(
        submit=AsyncMock(
            return_value=SubmissionResult(
                ok=False,
                error=FAILURE_AUTH_REQUIRED,
                error_message="Greenhouse cookie expired",
            )
        )
    )
    with patch("services.application_service.ats_dispatch", return_value=fake_adapter):
        out = await submit_draft(session, app_row.id)

    assert out.status == ApplicationStatus.DRAFT
    assert out.applied_at is None
    artifacts = out.submission_artifacts or {}
    last = artifacts.get("last_failure") or {}
    assert last.get("kind") == "auth_required"
    assert "Greenhouse" in last.get("message", "")
    assert artifacts.get("retry_count") == 1


@pytest.mark.asyncio
async def test_submit_draft_rate_limit_failure_classified():
    app_row = _make_app()
    session = _FakeSession()
    session.exec_queue = [
        _exec_one(app_row),
        _exec_count(0),
        _exec_one(None),  # sponsorship-gate Profile → None (plan 76)
        _exec_one(None),  # Settings load
        _exec_one(None),
        _exec_one(None),
        _exec_all([]),
    ]
    fake_adapter = SimpleNamespace(
        submit=AsyncMock(
            return_value=SubmissionResult(
                ok=False,
                error=FAILURE_RATE_LIMIT,
                error_message="429",
                retry_after=60,
            )
        )
    )
    with patch("services.application_service.ats_dispatch", return_value=fake_adapter):
        out = await submit_draft(session, app_row.id)
    assert out.submission_artifacts["last_failure"]["kind"] == "rate_limit"


@pytest.mark.asyncio
async def test_submit_draft_validates_first_raises_validation_error():
    """validate_submittable raises before the adapter is ever called."""
    from models import ApplicationStatus

    app_row = _make_app(status=ApplicationStatus.APPLIED)
    session = _FakeSession()
    session.exec_queue = [_exec_one(app_row)]
    with pytest.raises(ValidationError):
        await submit_draft(session, app_row.id)


# ── discard_draft ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_discard_draft_flips_to_closed_and_soft_deletes():
    from models import ApplicationStatus, ClosedReason

    app_row = _make_app()
    session = _FakeSession()
    session.exec_queue = [_exec_one(app_row), _exec_one(None)]  # app, then job lookup
    out = await discard_draft(session, app_row.id)
    assert out.status == ApplicationStatus.CLOSED
    assert out.closed_reason == ClosedReason.WITHDRAWN_BY_ME
    assert out.deleted_at is not None


@pytest.mark.asyncio
async def test_discard_rejects_non_draft():
    from models import ApplicationStatus

    app_row = _make_app(status=ApplicationStatus.APPLIED)
    session = _FakeSession()
    session.exec_queue = [_exec_one(app_row)]
    with pytest.raises(IllegalStateTransition):
        await discard_draft(session, app_row.id)


# ── process_auto_apply_queue ────────────────────────────────────────


@pytest.mark.asyncio
async def test_process_auto_apply_queue_dispatches_one_app():
    from models import ApplicationStatus, JobQueueState

    app_row = _make_app()
    job_row = _make_job(queue_state=JobQueueState.QUEUED_FOR_AUTO_APPLY)
    settings_row = SimpleNamespace(
        user_id=1,
        auto_apply_enabled=True,
        auto_apply_daily_cap=None,
    )

    session = _FakeSession()
    # Order: queue scan returns [(app, job)]; per-user settings lookup; submit_draft
    # is replaced via patch so its internal exec calls don't matter here.
    session.exec_queue = [
        _exec_all([(app_row, job_row)]),
        _exec_one(settings_row),
    ]

    fake_submit = AsyncMock()
    success_app = _make_app(status=ApplicationStatus.APPLIED, applied_at=datetime.now(UTC))
    fake_submit.return_value = success_app

    with patch("services.application_service.submit_draft", new=fake_submit):
        result = await process_auto_apply_queue(session)
    assert result.processed == 1
    assert result.submitted == 1
    assert result.failed == 0


@pytest.mark.asyncio
async def test_process_auto_apply_queue_respects_daily_cap():
    from models import JobQueueState

    app_row = _make_app()
    job_row = _make_job(queue_state=JobQueueState.QUEUED_FOR_AUTO_APPLY)
    settings_row = SimpleNamespace(
        user_id=1,
        auto_apply_enabled=True,
        auto_apply_daily_cap=1,  # cap reached after 1 submit
    )
    session = _FakeSession()
    session.exec_queue = [
        _exec_all([(app_row, job_row)]),
        _exec_one(settings_row),
        _exec_count(5),  # already submitted 5 today
    ]
    result = await process_auto_apply_queue(session)
    assert result.skipped_by_cap == 1
    assert result.submitted == 0


@pytest.mark.asyncio
async def test_process_auto_apply_queue_disabled_setting_skips():
    from models import JobQueueState

    app_row = _make_app()
    job_row = _make_job(queue_state=JobQueueState.QUEUED_FOR_AUTO_APPLY)
    settings_row = SimpleNamespace(
        user_id=1,
        auto_apply_enabled=False,
        auto_apply_daily_cap=None,
    )
    session = _FakeSession()
    session.exec_queue = [
        _exec_all([(app_row, job_row)]),
        _exec_one(settings_row),
    ]
    result = await process_auto_apply_queue(session)
    assert result.processed == 1
    assert result.submitted == 0


# ── update_status forward-only enforcement + manual override ──────


@pytest.mark.asyncio
async def test_update_status_requires_closed_reason_for_close():
    from models import ApplicationStatus

    app_row = _make_app(status=ApplicationStatus.APPLIED)
    session = _FakeSession()
    session.exec_queue = [_exec_one(app_row)]
    with pytest.raises(ValidationError):
        await update_status(session, app_row.id, ApplicationStatus.CLOSED)


@pytest.mark.asyncio
async def test_update_status_records_manual_override_for_backwards():
    """ONSITE_LOOP → APPLIED is allowed but logged as manual override."""
    from models import ApplicationStatus

    app_row = _make_app(status=ApplicationStatus.ONSITE_LOOP, applied_at=datetime.now(UTC))
    session = _FakeSession()
    session.exec_queue = [_exec_one(app_row)]
    out = await update_status(
        session, app_row.id, ApplicationStatus.APPLIED, notes="recruiter pulled back"
    )
    assert out.status == ApplicationStatus.APPLIED


# ── Computed state — referral rollup ────────────────────────────────


@pytest.mark.asyncio
async def test_roll_up_referral_state_picks_max():
    from models import ReferralState

    app_row = _make_app(referral_state=ReferralState.NONE)
    links = [
        SimpleNamespace(referral_state=ReferralState.REQUESTED),
        SimpleNamespace(referral_state=ReferralState.PROVIDED),
        SimpleNamespace(referral_state=ReferralState.IN_FLIGHT),
    ]
    session = _FakeSession()
    session.exec_queue = [_exec_all(links), _exec_one(app_row)]
    out = await _roll_up_referral_state(session, app_row.id)
    assert out == ReferralState.PROVIDED
    assert app_row.referral_state == ReferralState.PROVIDED


@pytest.mark.asyncio
async def test_roll_up_referral_state_no_links_is_none():
    from models import ReferralState

    app_row = _make_app(referral_state=ReferralState.REQUESTED)
    session = _FakeSession()
    session.exec_queue = [_exec_all([]), _exec_one(app_row)]
    out = await _roll_up_referral_state(session, app_row.id)
    assert out == ReferralState.NONE


# ── Computed outreach engagement ────────────────────────────────────


@pytest.mark.asyncio
async def test_compute_outreach_engagement_referred():
    from models import ReferralState

    links = [SimpleNamespace(referral_state=ReferralState.PROVIDED)]
    session = _FakeSession()
    session.exec_queue = [_exec_all(links)]
    assert await compute_outreach_engagement(session, 1) == "referred"


@pytest.mark.asyncio
async def test_compute_outreach_engagement_awaiting_reply():
    from models import OutreachStatus, ReferralState

    links = [SimpleNamespace(referral_state=ReferralState.NONE)]
    msgs = [
        SimpleNamespace(
            sent_at=datetime.now(UTC) - timedelta(days=2),
            replied_at=None,
            status=OutreachStatus.SENT,
        )
    ]
    session = _FakeSession()
    session.exec_queue = [_exec_all(links), _exec_all(msgs)]
    assert await compute_outreach_engagement(session, 1) == "awaiting_reply"


@pytest.mark.asyncio
async def test_compute_outreach_engagement_cold_when_empty():
    session = _FakeSession()
    session.exec_queue = [_exec_all([]), _exec_all([])]
    assert await compute_outreach_engagement(session, 1) == "cold"


# ── Stuck queue surface ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stuck_drafts_filters_to_apps_with_last_failure():
    failed = _make_app(submission_artifacts={"last_failure": {"kind": "auth_required"}})
    clean = _make_app(submission_artifacts=None)
    session = _FakeSession()
    session.exec_queue = [_exec_all([failed, clean])]
    rows = await svc.stuck_drafts(session, user_id=1)
    assert len(rows) == 1
    assert rows[0] is failed


# ── Plan 79 / 0.4.0.11 — retry-failed-application ───────────────────


@pytest.mark.asyncio
async def test_retry_failed_clears_last_failure():
    """DRAFT with `last_failure` → retry strips the marker; retry_count preserved."""
    app_row = _make_app(
        submission_artifacts={
            "last_failure": {"kind": "rate_limit", "message": "429"},
            "retry_count": 2,
        }
    )
    session = _FakeSession()
    session.exec_queue = [_exec_one(app_row), _exec_one(None)]  # app load; no Job lookup needed
    # Re-queue path requires Job lookup; supply None so we skip it.

    out = await svc.retry_failed(session, app_row.id, user_id=1)
    assert "last_failure" not in (out.submission_artifacts or {})
    assert out.submission_artifacts.get("retry_count") == 2


@pytest.mark.asyncio
async def test_retry_failed_requeues_when_auto_apply_enabled():
    """Job in SAVED + Settings.auto_apply_enabled=True → Job flips to QUEUED_FOR_AUTO_APPLY."""
    from models import JobQueueState

    app_row = _make_app(
        submission_artifacts={"last_failure": {"kind": "unknown", "message": "boom"}}
    )
    job_row = _make_job(queue_state=JobQueueState.SAVED)
    settings_row = _make_settings(auto_apply_enabled=True)
    session = _FakeSession()
    session.exec_queue = [
        _exec_one(app_row),  # get_application
        _exec_one(job_row),  # Job lookup
        _exec_one(settings_row),  # Settings lookup
    ]

    await svc.retry_failed(session, app_row.id, user_id=1)
    assert job_row.queue_state == JobQueueState.QUEUED_FOR_AUTO_APPLY


@pytest.mark.asyncio
async def test_retry_failed_no_requeue_when_auto_apply_disabled():
    """Job in SAVED + Settings.auto_apply_enabled=False → Job stays SAVED."""
    from models import JobQueueState

    app_row = _make_app(
        submission_artifacts={"last_failure": {"kind": "captcha", "message": "blocked"}}
    )
    job_row = _make_job(queue_state=JobQueueState.SAVED)
    settings_row = _make_settings(auto_apply_enabled=False)
    session = _FakeSession()
    session.exec_queue = [
        _exec_one(app_row),
        _exec_one(job_row),
        _exec_one(settings_row),
    ]

    await svc.retry_failed(session, app_row.id, user_id=1)
    assert job_row.queue_state == JobQueueState.SAVED


@pytest.mark.asyncio
async def test_retry_failed_rejects_non_draft():
    """status=APPLIED → IllegalStateTransition (route → 409)."""
    from models import ApplicationStatus

    app_row = _make_app(
        status=ApplicationStatus.APPLIED,
        submission_artifacts={"last_failure": {"kind": "unknown", "message": "x"}},
    )
    session = _FakeSession()
    session.exec_queue = [_exec_one(app_row)]
    with pytest.raises(IllegalStateTransition):
        await svc.retry_failed(session, app_row.id, user_id=1)


@pytest.mark.asyncio
async def test_retry_failed_rejects_no_failure():
    """DRAFT with empty artifacts → IllegalStateTransition (route → 409)."""
    app_row = _make_app(submission_artifacts={})
    session = _FakeSession()
    session.exec_queue = [_exec_one(app_row)]
    with pytest.raises(IllegalStateTransition):
        await svc.retry_failed(session, app_row.id, user_id=1)


@pytest.mark.asyncio
async def test_retry_failed_idor_returns_404():
    """Cross-user attempt → ApplicationServiceError (route swallows → 404)."""
    app_row = _make_app(
        user_id=2,
        submission_artifacts={"last_failure": {"kind": "unknown", "message": "x"}},
    )
    session = _FakeSession()
    session.exec_queue = [_exec_one(app_row)]
    with pytest.raises(svc.ApplicationServiceError):
        await svc.retry_failed(session, app_row.id, user_id=1)


# ── Plan 80 / 0.4.0.09 — bulk actions on /tracking list ─────────────


@pytest.mark.asyncio
async def test_bulk_update_status_forward_only_skips_backwards():
    """Backwards transitions surface in the failed list, not the success count."""
    from models import ApplicationStatus

    a1 = _make_app(aid=1, status=ApplicationStatus.APPLIED, applied_at=datetime.now(UTC))
    a2 = _make_app(aid=2, status=ApplicationStatus.OFFER, applied_at=datetime.now(UTC))
    session = _FakeSession()
    # bulk_update_status loads app, then update_status loads it again — 2 exec/id.
    session.exec_queue = [
        _exec_one(a1),  # bulk: load a1
        _exec_one(a1),  # update_status: re-load a1 (forward OFFER target → fail)
        _exec_one(a2),  # bulk: load a2
        _exec_one(a2),  # update_status: re-load a2 (OFFER → CLOSED missing reason → fail)
    ]

    success, failed = await svc.bulk_update_status(
        session,
        user_id=1,
        application_ids=[1, 2],
        new_status=ApplicationStatus.CLOSED,
    )
    # closed_reason is None → ValidationError on every CLOSED transition; both fail.
    assert success == 0
    assert sorted(failed) == [1, 2]


@pytest.mark.asyncio
async def test_bulk_update_status_cross_user_silent_fail():
    """IDOR — cross-user IDs surface in failed list without raising."""
    from models import ApplicationStatus

    mine = _make_app(aid=10, status=ApplicationStatus.APPLIED, applied_at=datetime.now(UTC))
    yours = _make_app(aid=11, user_id=2, status=ApplicationStatus.APPLIED)
    session = _FakeSession()
    session.exec_queue = [
        _exec_one(mine),
        _exec_one(mine),  # update_status re-load
        _exec_one(yours),  # bulk: cross-user → goes straight to failed (no re-load)
    ]
    success, failed = await svc.bulk_update_status(
        session,
        user_id=1,
        application_ids=[10, 11],
        new_status=ApplicationStatus.RECRUITER_SCREEN,
    )
    assert success == 1
    assert failed == [11]


@pytest.mark.asyncio
async def test_bulk_archive_sets_user_archived_reason():
    """bulk_archive — APPLIED → CLOSED w/ closed_reason=USER_ARCHIVED."""
    from models import ApplicationStatus, ClosedReason

    a = _make_app(aid=42, status=ApplicationStatus.APPLIED, applied_at=datetime.now(UTC))
    session = _FakeSession()
    session.exec_queue = [_exec_one(a), _exec_one(a)]
    success, failed = await svc.bulk_archive(
        session, user_id=1, application_ids=[42]
    )
    assert success == 1
    assert failed == []
    assert a.status == ApplicationStatus.CLOSED
    assert a.closed_reason == ClosedReason.USER_ARCHIVED


@pytest.mark.asyncio
async def test_bulk_update_rejects_over_50_ids():
    """Cap at 50 IDs — raises ValidationError before any DB work."""
    from models import ApplicationStatus

    session = _FakeSession()
    ids = list(range(1, 52))  # 51 IDs
    with pytest.raises(ValidationError) as exc:
        await svc.bulk_update_status(
            session,
            user_id=1,
            application_ids=ids,
            new_status=ApplicationStatus.RECRUITER_SCREEN,
        )
    assert exc.value.code == "bulk_limit_exceeded"
    assert session.exec_queue == []  # no DB load on cap rejection


@pytest.mark.asyncio
async def test_bulk_export_csv_includes_only_authorized_apps():
    """list_for_export — single SELECT, owner-only rows surface."""
    from models import ApplicationStatus

    a1 = _make_app(aid=1, status=ApplicationStatus.APPLIED, applied_at=datetime.now(UTC))
    a2 = _make_app(aid=2, status=ApplicationStatus.RECRUITER_SCREEN, applied_at=datetime.now(UTC))
    session = _FakeSession()
    session.exec_queue = [_exec_all([a1, a2])]
    rows = await svc.list_for_export(session, user_id=1, application_ids=[1, 2])
    assert len(rows) == 2
    assert rows[0]["company"] == "Stripe"
    assert rows[0]["status"] == "APPLIED"
    assert rows[1]["status"] == "RECRUITER_SCREEN"
    assert rows[0]["board"] == "greenhouse"
    assert "applied_at" in rows[0]


@pytest.mark.asyncio
async def test_bulk_export_csv_idor_filters():
    """Cross-user IDs filtered by service-layer WHERE clause; not in CSV."""
    from models import ApplicationStatus

    # The fake-session exec returns only what the DB would — emulate the
    # SQL filter by passing back just the owner's row.
    mine = _make_app(aid=10, status=ApplicationStatus.APPLIED, applied_at=datetime.now(UTC))
    session = _FakeSession()
    session.exec_queue = [_exec_all([mine])]
    rows = await svc.list_for_export(
        session, user_id=1, application_ids=[10, 99]  # 99 is another user's
    )
    assert len(rows) == 1
    assert rows[0]["company"] == "Stripe"


@pytest.mark.asyncio
async def test_retry_failed_emits_app_event():
    """Successful retry emits AUTO_APPLY_QUEUED with trigger=retry_requested + previous_retry_count."""
    from models import AppEvent, AppEventKind

    app_row = _make_app(
        submission_artifacts={
            "last_failure": {"kind": "low_confidence", "message": "0.6 < 0.7"},
            "retry_count": 3,
        }
    )
    session = _FakeSession()
    session.exec_queue = [_exec_one(app_row), _exec_one(None)]

    await svc.retry_failed(session, app_row.id, user_id=1)
    events = [obj for obj in session.added if isinstance(obj, AppEvent)]
    assert len(events) == 1
    ev = events[0]
    assert ev.kind == AppEventKind.AUTO_APPLY_QUEUED
    assert ev.payload["trigger"] == "retry_requested"
    assert ev.payload["previous_retry_count"] == 3


# ── Plan 77 / 0.4.0.17 — notification parity on manual submit_draft ──


@pytest.mark.asyncio
async def test_submit_draft_default_notify_fn_fires_when_settings_configured():
    """No explicit notify_fn + Settings present → default `notify_application_submitted` fires.

    Proves the HTTP submit-draft path now gets the same Discord/Telegram echo
    that auto-apply cron already had. Manual + auto submissions now parity.
    """
    from models import ApplicationStatus, JobQueueState

    app_row = _make_app()
    job_row = _make_job()
    settings_row = _make_settings()  # has notifications keys, used by closure

    session = _FakeSession()
    # exec sequence — same as the happy-path success test, with Settings load
    # returning a real-ish settings object instead of None.
    session.exec_queue = [
        _exec_one(app_row),
        _exec_count(0),
        _exec_one(None),  # sponsorship-gate Profile → None
        _exec_one(settings_row),  # Settings load
        _exec_one(None),
        _exec_one(None),
        _exec_all([]),
        _exec_one(job_row),
    ]

    fake_adapter = SimpleNamespace(
        submit=AsyncMock(return_value=SubmissionResult(ok=True, board_application_id="GH-12345"))
    )
    notify_application_submitted = AsyncMock()

    with (
        patch("services.application_service.ats_dispatch", return_value=fake_adapter),
        patch(
            "services.notifications.notify_application_submitted", new=notify_application_submitted
        ),
    ):
        out = await submit_draft(session, app_row.id)

    assert out.status == ApplicationStatus.APPLIED
    assert job_row.queue_state == JobQueueState.APPLIED
    notify_application_submitted.assert_awaited_once()
    kwargs = notify_application_submitted.call_args.kwargs
    assert kwargs["settings"] is settings_row
    assert kwargs["application"] is app_row


@pytest.mark.asyncio
async def test_submit_draft_default_notify_fn_skipped_when_no_settings():
    """No Settings row → default helper returns None → no notification fires.

    Manual submission with a brand-new user who hasn't configured Settings
    yet should NOT raise; it should silently skip the channel send.
    """
    from models import ApplicationStatus

    app_row = _make_app()
    job_row = _make_job()
    session = _FakeSession()
    session.exec_queue = [
        _exec_one(app_row),
        _exec_count(0),
        _exec_one(None),  # sponsorship-gate Profile → None
        _exec_one(None),  # Settings load → None
        _exec_one(None),
        _exec_one(None),
        _exec_all([]),
        _exec_one(job_row),
    ]

    fake_adapter = SimpleNamespace(
        submit=AsyncMock(return_value=SubmissionResult(ok=True, board_application_id="GH-12345"))
    )
    notify_application_submitted = AsyncMock()

    with (
        patch("services.application_service.ats_dispatch", return_value=fake_adapter),
        patch(
            "services.notifications.notify_application_submitted", new=notify_application_submitted
        ),
    ):
        out = await submit_draft(session, app_row.id)

    assert out.status == ApplicationStatus.APPLIED
    notify_application_submitted.assert_not_awaited()


@pytest.mark.asyncio
async def test_submit_draft_explicit_notify_fn_overrides_default():
    """Explicit `notify_fn` (auto-apply cron path) wins over the default closure.

    Regression test for the cron caller in `scheduler/jobs.py:54`. Confirms the
    new default-helper plumbing did not change behavior for callers that
    already thread `notify_fn`.
    """
    from models import ApplicationStatus

    app_row = _make_app()
    job_row = _make_job()
    settings_row = _make_settings()
    session = _FakeSession()
    session.exec_queue = [
        _exec_one(app_row),
        _exec_count(0),
        _exec_one(None),  # sponsorship-gate Profile → None
        _exec_one(settings_row),  # Settings load
        _exec_one(None),
        _exec_one(None),
        _exec_all([]),
        _exec_one(job_row),
    ]

    fake_adapter = SimpleNamespace(
        submit=AsyncMock(return_value=SubmissionResult(ok=True, board_application_id="GH-12345"))
    )
    explicit_notify = AsyncMock()
    default_notify_application_submitted = AsyncMock()

    with (
        patch("services.application_service.ats_dispatch", return_value=fake_adapter),
        patch(
            "services.notifications.notify_application_submitted",
            new=default_notify_application_submitted,
        ),
    ):
        out = await submit_draft(session, app_row.id, notify_fn=explicit_notify)

    assert out.status == ApplicationStatus.APPLIED
    # Explicit closure ran; the default factory's underlying helper did not.
    explicit_notify.assert_awaited_once_with(app_row)
    default_notify_application_submitted.assert_not_awaited()


# ── Plan 78 — Auto-apply hardening (0.4.0.04/13/14/15/20/22) ─────────


def _make_auto_apply_settings(**kw):
    base = {
        "user_id": 1,
        "auto_apply_enabled": True,
        "auto_apply_daily_cap": None,
        "auto_apply_score_threshold": 0.7,
        "auto_apply_per_board_daily_caps": {},
        "auto_apply_dry_run": False,
    }
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_process_auto_apply_queue_score_threshold_pulls_below_threshold():
    """Plan 78 § D.1 — Job.score below Settings.auto_apply_score_threshold ⇒
    cron pulls Job back to SAVED + skips dispatch. submit_draft is NOT called.
    """
    from models import JobQueueState

    app_row = _make_app()
    # Job scored 0.40 but threshold is 0.85 → drift below threshold scenario.
    job_row = _make_job(queue_state=JobQueueState.QUEUED_FOR_AUTO_APPLY, score=0.40)
    settings_row = _make_auto_apply_settings(auto_apply_score_threshold=0.85)
    session = _FakeSession()
    session.exec_queue = [
        _exec_all([(app_row, job_row)]),
        _exec_one(settings_row),
    ]

    fake_submit = AsyncMock()
    with patch("services.application_service.submit_draft", new=fake_submit):
        result = await process_auto_apply_queue(session)

    assert result.processed == 1
    assert result.submitted == 0
    fake_submit.assert_not_awaited()
    assert job_row.queue_state == JobQueueState.SAVED


@pytest.mark.asyncio
async def test_process_auto_apply_queue_score_threshold_passes_at_or_above():
    """Score equal to threshold → cron proceeds; submit_draft runs."""
    from models import ApplicationStatus, JobQueueState

    app_row = _make_app()
    job_row = _make_job(queue_state=JobQueueState.QUEUED_FOR_AUTO_APPLY, score=0.85)
    settings_row = _make_auto_apply_settings(auto_apply_score_threshold=0.85)
    session = _FakeSession()
    session.exec_queue = [
        _exec_all([(app_row, job_row)]),
        _exec_one(settings_row),
    ]
    fake_submit = AsyncMock()
    success_app = _make_app(status=ApplicationStatus.APPLIED, applied_at=datetime.now(UTC))
    fake_submit.return_value = success_app

    with patch("services.application_service.submit_draft", new=fake_submit):
        result = await process_auto_apply_queue(session)

    assert result.submitted == 1
    fake_submit.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_auto_apply_queue_per_board_cap_respected():
    """Plan 78 § D.3 — per-board cap binds when daily count meets per-board limit."""
    from models import JobQueueState

    app_row = _make_app()  # board=GREENHOUSE
    job_row = _make_job(queue_state=JobQueueState.QUEUED_FOR_AUTO_APPLY, score=0.9)
    settings_row = _make_auto_apply_settings(
        auto_apply_per_board_daily_caps={"greenhouse": 2},
    )
    session = _FakeSession()
    session.exec_queue = [
        _exec_all([(app_row, job_row)]),
        _exec_one(settings_row),
        # validate_submittable: screener count → 0
        _exec_count(0),
        # validate_submittable: sponsorship-gate Profile → None
        _exec_one(None),
        # per-board today count → already at the cap (2 of 2)
        _exec_count(2),
    ]
    fake_submit = AsyncMock()
    with patch("services.application_service.submit_draft", new=fake_submit):
        result = await process_auto_apply_queue(session)

    assert result.skipped_by_cap == 1
    assert result.submitted == 0
    fake_submit.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_auto_apply_queue_per_board_cap_skipped_when_unset():
    """Empty per-board dict → fall through to global cap (also None here)."""
    from models import ApplicationStatus, JobQueueState

    app_row = _make_app()
    job_row = _make_job(queue_state=JobQueueState.QUEUED_FOR_AUTO_APPLY, score=0.9)
    settings_row = _make_auto_apply_settings(auto_apply_per_board_daily_caps={})
    session = _FakeSession()
    session.exec_queue = [
        _exec_all([(app_row, job_row)]),
        _exec_one(settings_row),
        # validate_submittable: screener count → 0
        _exec_count(0),
        # validate_submittable: sponsorship-gate Profile → None
        _exec_one(None),
    ]
    fake_submit = AsyncMock()
    fake_submit.return_value = _make_app(
        status=ApplicationStatus.APPLIED, applied_at=datetime.now(UTC)
    )
    with patch("services.application_service.submit_draft", new=fake_submit):
        result = await process_auto_apply_queue(session)
    assert result.submitted == 1


@pytest.mark.asyncio
async def test_process_auto_apply_queue_dry_run_short_circuits_before_submit():
    """Plan 78 § D.5 — dry-run flag stamps submission_artifacts.dry_run_at
    and emits AUTO_APPLY_DRY_RUN event WITHOUT calling submit_draft.
    """
    from models import AppEventKind, JobQueueState

    app_row = _make_app()
    job_row = _make_job(queue_state=JobQueueState.QUEUED_FOR_AUTO_APPLY, score=0.9)
    settings_row = _make_auto_apply_settings(auto_apply_dry_run=True)
    session = _FakeSession()
    session.exec_queue = [
        _exec_all([(app_row, job_row)]),
        _exec_one(settings_row),
        # validate_submittable: screener count → 0
        _exec_count(0),
        # validate_submittable: sponsorship-gate Profile → None (short-circuits)
        _exec_one(None),
    ]
    fake_submit = AsyncMock()
    with patch("services.application_service.submit_draft", new=fake_submit):
        result = await process_auto_apply_queue(session)

    fake_submit.assert_not_awaited()
    assert result.processed == 1
    assert result.submitted == 0
    artifacts = app_row.submission_artifacts or {}
    assert artifacts.get("dry_run_at") is not None
    # AppEvent emitted with kind=AUTO_APPLY_DRY_RUN
    events = [obj for obj in session.added if hasattr(obj, "kind")]
    assert any(e.kind == AppEventKind.AUTO_APPLY_DRY_RUN for e in events)


@pytest.mark.asyncio
async def test_process_auto_apply_queue_visa_blocked_dequeues_and_emits_event():
    """Plan 78 fold-in (0.4.0.22) — visa_incompatible ValidationError pulls Job
    out of queue + emits AUTO_APPLY_VISA_BLOCKED so cron doesn't tight-loop.
    """
    from models import AppEventKind, JobQueueState

    app_row = _make_app()
    job_row = _make_job(queue_state=JobQueueState.QUEUED_FOR_AUTO_APPLY, score=0.9)
    settings_row = _make_auto_apply_settings()
    session = _FakeSession()
    session.exec_queue = [
        _exec_all([(app_row, job_row)]),
        _exec_one(settings_row),
    ]

    async def _raise_visa(_session, _application):
        raise ValidationError("visa blocked", code="visa_incompatible")

    with patch("services.application_service.validate_submittable", new=_raise_visa):
        result = await process_auto_apply_queue(session)

    assert result.processed == 1
    assert result.submitted == 0
    assert job_row.queue_state == JobQueueState.SAVED
    events = [obj for obj in session.added if hasattr(obj, "kind")]
    assert any(e.kind == AppEventKind.AUTO_APPLY_VISA_BLOCKED for e in events)


@pytest.mark.asyncio
async def test_process_auto_apply_queue_other_validation_error_does_not_dequeue():
    """Non-visa ValidationError (e.g. docs_not_ready) leaves Job queued."""
    from models import JobQueueState

    app_row = _make_app()
    job_row = _make_job(queue_state=JobQueueState.QUEUED_FOR_AUTO_APPLY, score=0.9)
    settings_row = _make_auto_apply_settings()
    session = _FakeSession()
    session.exec_queue = [
        _exec_all([(app_row, job_row)]),
        _exec_one(settings_row),
    ]

    async def _raise_unready(_session, _application):
        raise ValidationError("docs not ready", code="docs_not_ready")

    with patch("services.application_service.validate_submittable", new=_raise_unready):
        result = await process_auto_apply_queue(session)

    assert result.submitted == 0
    # Stays QUEUED — not visa-incompatible, so cron leaves the job alone
    # so the next tick can pick it up after the unready cond clears.
    assert job_row.queue_state == JobQueueState.QUEUED_FOR_AUTO_APPLY


@pytest.mark.asyncio
async def test_submit_draft_low_confidence_keeps_draft_and_records_failure():
    """Plan 78 § D.2 — adapter confidence < threshold ⇒ revert to DRAFT +
    record `low_confidence` failure kind. APPLIED branch not entered.
    """
    from models import ApplicationStatus

    app_row = _make_app()
    settings_row = _make_settings(auto_apply_adapter_confidence_threshold=0.8)
    session = _FakeSession()
    session.exec_queue = [
        _exec_one(app_row),
        _exec_count(0),
        _exec_one(None),  # sponsorship-gate Profile → None
        _exec_one(settings_row),  # Settings load
        _exec_one(None),  # resume
        _exec_one(None),  # cover
        _exec_all([]),  # screeners
    ]
    fake_adapter = SimpleNamespace(
        submit=AsyncMock(
            return_value=SubmissionResult(
                ok=True,
                board_application_id="X-1",
                confidence=0.5,  # below threshold 0.8
                raw={"request_url": "https://x"},
            )
        )
    )

    with patch("services.application_service.ats_dispatch", return_value=fake_adapter):
        out = await submit_draft(session, app_row.id)

    assert out.status == ApplicationStatus.DRAFT
    artifacts = out.submission_artifacts or {}
    last = artifacts.get("last_failure") or {}
    assert last.get("kind") == "low_confidence"


@pytest.mark.asyncio
async def test_submit_draft_full_confidence_proceeds():
    """HTTP adapters always emit confidence=1.0; passes any threshold."""
    from models import ApplicationStatus, JobQueueState

    app_row = _make_app()
    job_row = _make_job()
    settings_row = _make_settings(auto_apply_adapter_confidence_threshold=0.8)
    session = _FakeSession()
    session.exec_queue = [
        _exec_one(app_row),
        _exec_count(0),
        _exec_one(None),  # sponsorship-gate Profile
        _exec_one(settings_row),
        _exec_one(None),
        _exec_one(None),
        _exec_all([]),
        _exec_one(job_row),
    ]
    fake_adapter = SimpleNamespace(
        submit=AsyncMock(
            return_value=SubmissionResult(ok=True, board_application_id="GH-1", confidence=1.0)
        )
    )
    with patch("services.application_service.ats_dispatch", return_value=fake_adapter):
        out = await submit_draft(session, app_row.id, notify_fn=AsyncMock())

    assert out.status == ApplicationStatus.APPLIED
    assert job_row.queue_state == JobQueueState.APPLIED


@pytest.mark.asyncio
async def test_drain_auto_apply_queue_flips_all_queued():
    """Plan 78 § D.4 — drain helper flips every QUEUED_FOR_AUTO_APPLY Job back
    to SAVED + emits one AUTO_APPLY_DRAINED event per Application.
    """
    from models import AppEventKind, JobQueueState

    app1 = _make_app(aid=1)
    app2 = _make_app(aid=2)
    job1 = _make_job(jid=11, queue_state=JobQueueState.QUEUED_FOR_AUTO_APPLY)
    job2 = _make_job(jid=12, queue_state=JobQueueState.QUEUED_FOR_AUTO_APPLY)
    session = _FakeSession()
    session.exec_queue = [_exec_all([(app1, job1), (app2, job2)])]

    drained = await svc.drain_auto_apply_queue(session, user_id=1, reason="settings_drain")

    assert drained == 2
    assert job1.queue_state == JobQueueState.SAVED
    assert job2.queue_state == JobQueueState.SAVED
    events = [obj for obj in session.added if hasattr(obj, "kind")]
    drained_events = [e for e in events if e.kind == AppEventKind.AUTO_APPLY_DRAINED]
    assert len(drained_events) == 2


@pytest.mark.asyncio
async def test_pause_auto_apply_for_job_flips_queued_to_saved():
    """Plan 78 § D.4 — per-job pause: QUEUED → SAVED."""
    from models import JobQueueState

    job_row = _make_job(jid=42, queue_state=JobQueueState.QUEUED_FOR_AUTO_APPLY)
    job_row.user_id = 1
    job_row.deleted_at = None
    session = _FakeSession()
    session.exec_queue = [_exec_one(job_row)]

    out = await svc.pause_auto_apply_for_job(session, user_id=1, job_id=42)

    assert out is job_row
    assert out.queue_state == JobQueueState.SAVED


@pytest.mark.asyncio
async def test_pause_auto_apply_for_job_returns_none_for_unknown_job():
    session = _FakeSession()
    session.exec_queue = [_exec_one(None)]
    out = await svc.pause_auto_apply_for_job(session, user_id=1, job_id=999)
    assert out is None


@pytest.mark.asyncio
async def test_pause_auto_apply_for_job_no_op_when_not_queued():
    """If Job is already SAVED (not queued), pause helper is a no-op."""
    from models import JobQueueState

    job_row = _make_job(jid=42, queue_state=JobQueueState.SAVED)
    job_row.user_id = 1
    job_row.deleted_at = None
    session = _FakeSession()
    session.exec_queue = [_exec_one(job_row)]

    out = await svc.pause_auto_apply_for_job(session, user_id=1, job_id=42)

    assert out is job_row
    assert out.queue_state == JobQueueState.SAVED  # unchanged
