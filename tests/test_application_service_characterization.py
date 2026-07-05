"""Plan 91 Phase 3.1 — application_service characterization (sqlite tier).

Behaviour-pinning BEFORE the Phase-4 split of `services/application_service.py`.
Unlike the FakeSession suites (`test_application_service.py`,
`test_auto_apply_pipeline.py`) these run the real SQL against a seeded sqlite
session, so the queries themselves are exercised — the tests that must stay
green, unchanged, when the module is decomposed behind facades:

- the status-transition matrix (`_FORWARD_FROM` + manual-override semantics)
- the AppEvent emission contract per mutation (draft creation, queueing,
  status flips, discard)
- `process_auto_apply_queue` stage outcomes (docs generation, honest
  handoffs, score drift, daily cap, visa gate, in-flight docs)

Only the process-boundary seams are patched (`bundle_generator.generate_bundle`,
`application_service.submit_draft`) — both are facade-preserved patch targets.
"""

from __future__ import annotations

import enum
import json
from datetime import UTC, datetime, timedelta
from itertools import product
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text
from sqlmodel import select

from models import (
    AppEvent,
    Application,
    ApplicationScreenerAnswer,
    Bullet,
    Experience,
    GeneratedDocument,
    Job,
    Profile,
    Settings,
    User,
)
from models.enums import (
    AppEventKind,
    ApplicationBoard,
    ApplicationStatus,
    ClosedReason,
    DocsState,
    JobQueueState,
    JobSource,
    StatusChangeTrigger,
    VisaRestriction,
    VisaSponsorship,
)
from services import applications as application_service
from services.applications import (
    _FORWARD_FROM,
    ApplicationServiceError,
    IllegalStateTransition,
    ValidationError,
    discard_draft,
    get_or_create_draft,
    process_auto_apply_queue,
    queue_auto_apply,
    update_status,
)
from tests._sqlite import sqlite_session, strip_pg_checks

_NOW = datetime(2026, 7, 4, 12, 0, tzinfo=UTC)

_TABLES = strip_pg_checks(
    (
        User,
        Profile,
        Experience,
        Bullet,
        Job,
        Settings,
        Application,
        GeneratedDocument,
        ApplicationScreenerAnswer,
        AppEvent,
    )
)


@pytest.fixture
async def session():
    async with sqlite_session(tables=_TABLES) as s:
        s.add(User(id=1, email="owner@t.test", password_hash="x"))
        await s.flush()
        yield s


# ── Raw-insert helper for ARRAY-bearing models ──────────────────────────
# sqlite can't bind Python lists through the Postgres ARRAY type (the
# tests/_sqlite compiler shim only fixes DDL), so Job / Profile / Settings
# rows go in as raw SQL built from a model instance's Python defaults —
# same trick as tests/test_cross_user_idor_sweep.py, generalized.


async def _raw_insert(session, obj) -> int:
    table = type(obj).__table__
    params: dict[str, object] = {}
    for col in table.columns:
        if col.name == "id":
            continue
        v = getattr(obj, col.name, None)
        if isinstance(v, enum.Enum):
            v = v.name  # sa.Enum persists member names
        elif isinstance(v, (list, dict)):
            v = json.dumps(v)
        elif isinstance(v, datetime):
            v = v.isoformat(sep=" ")
        params[col.name] = v
    names = ", ".join(params)
    placeholders = ", ".join(f":{n}" for n in params)
    await session.execute(
        text(f"INSERT INTO {table.name} ({names}) VALUES ({placeholders})"), params
    )
    row_id = (await session.execute(text("SELECT last_insert_rowid()"))).scalar()
    return int(row_id)


async def _seed_job(session, **overrides) -> Job:
    base = {
        "user_id": 1,
        "source": JobSource.MANUAL,
        "external_id": f"x-{overrides.get('company', 'acme')}",
        "board": ApplicationBoard.GREENHOUSE,
        "url": "https://example.com/job",
        "url_type": "external",
        "company": "Acme",
        "role": "Software Engineer",
        "description": "d",
        "score": 0.9,
        "found_at": _NOW,
        "created_at": _NOW,
        "updated_at": _NOW,
    }
    base.update(overrides)
    job_id = await _raw_insert(session, Job(**base))
    return (await session.exec(select(Job).where(Job.id == job_id))).one()


async def _seed_settings(session, **overrides) -> Settings:
    s = Settings(user_id=1, created_at=_NOW, updated_at=_NOW)
    for k, v in overrides.items():
        setattr(s, k, v)
    await _raw_insert(session, s)  # PK is user_id — no autoincrement id
    return (await session.exec(select(Settings).where(Settings.user_id == s.user_id))).one()


async def _seed_profile(session, **overrides) -> int:
    p = Profile(
        user_id=1,
        full_name="Owner",
        headline="Eng",
        email="owner@t.test",
        created_at=_NOW,
        updated_at=_NOW,
    )
    for k, v in overrides.items():
        setattr(p, k, v)
    return await _raw_insert(session, p)


def _make_app(**overrides) -> Application:
    base = {
        "user_id": 1,
        "company": "Acme",
        "role": "Software Engineer",
        "status": ApplicationStatus.DRAFT,
        "docs_state": DocsState.NONE,
        "board": ApplicationBoard.GREENHOUSE,
        "created_at": _NOW,
        "updated_at": _NOW,
    }
    base.update(overrides)
    # ck_application_applied_at_required: non-DRAFT rows must carry applied_at.
    if base["status"] != ApplicationStatus.DRAFT and "applied_at" not in overrides:
        base["applied_at"] = _NOW
    return Application(**base)


async def _events(session, kind: AppEventKind | None = None) -> list[AppEvent]:
    stmt = select(AppEvent)
    if kind is not None:
        stmt = stmt.where(AppEvent.kind == kind)
    return list((await session.exec(stmt)).all())


# ── Status-transition matrix ────────────────────────────────────────────

_ALL = [
    ApplicationStatus.DRAFT,
    ApplicationStatus.APPLIED,
    ApplicationStatus.RECRUITER_SCREEN,
    ApplicationStatus.ONSITE_LOOP,
    ApplicationStatus.OFFER,
    ApplicationStatus.CLOSED,
]

_MATRIX = [(frm, to) for frm, to in product(_ALL, _ALL) if frm != to]


@pytest.mark.asyncio
@pytest.mark.parametrize("frm,to", _MATRIX, ids=[f"{f.value}->{t.value}" for f, t in _MATRIX])
async def test_status_transition_matrix(session, frm, to):
    """Every (from, to) pair flips the status; forwardness is recorded on the
    STATUS_CHANGE event, and backwards moves are allowed as manual overrides
    (never rejected)."""
    app = _make_app(
        status=frm,
        # ck_application_closed_reason_required: CLOSED rows must carry a reason.
        closed_reason=ClosedReason.REJECTED_BY_THEM if frm == ApplicationStatus.CLOSED else None,
    )
    session.add(app)
    await session.flush()

    result = await update_status(
        session,
        app.id,
        to,
        closed_reason=ClosedReason.REJECTED_BY_THEM if to == ApplicationStatus.CLOSED else None,
    )

    assert result.status == to
    if to == ApplicationStatus.CLOSED:
        assert result.closed_reason == ClosedReason.REJECTED_BY_THEM
    if to != ApplicationStatus.DRAFT:
        assert result.applied_at is not None  # leaving/entering non-DRAFT sets it

    events = await _events(session, AppEventKind.STATUS_CHANGE)
    assert len(events) == 1
    payload = events[0].payload
    assert payload["from"] == frm.value
    assert payload["to"] == to.value
    assert payload["trigger"] == StatusChangeTrigger.MANUAL.value
    assert payload["is_forward"] == (to in _FORWARD_FROM.get(frm, set()))


@pytest.mark.asyncio
async def test_update_status_close_requires_reason(session):
    app = _make_app(status=ApplicationStatus.APPLIED, applied_at=_NOW)
    session.add(app)
    await session.flush()
    with pytest.raises(ValidationError) as exc:
        await update_status(session, app.id, ApplicationStatus.CLOSED)
    assert exc.value.code == "closed_reason_missing"
    # No event emitted, status untouched.
    assert await _events(session) == []
    assert app.status == ApplicationStatus.APPLIED


@pytest.mark.asyncio
async def test_update_status_unknown_application_raises(session):
    with pytest.raises(ApplicationServiceError):
        await update_status(session, 999, ApplicationStatus.APPLIED)


@pytest.mark.asyncio
async def test_update_status_preserves_existing_applied_at(session):
    earlier = _NOW - timedelta(days=3)
    app = _make_app(status=ApplicationStatus.APPLIED, applied_at=earlier)
    session.add(app)
    await session.flush()
    result = await update_status(session, app.id, ApplicationStatus.RECRUITER_SCREEN)
    assert result.applied_at.replace(tzinfo=UTC) == earlier


# ── AppEvent emission per mutation ──────────────────────────────────────


@pytest.mark.asyncio
async def test_get_or_create_draft_emits_creation_event_once(session):
    job = await _seed_job(session)
    settings = await _seed_settings(session)

    draft = await get_or_create_draft(session, user_id=1, job_id=job.id, settings=settings)
    assert draft.status == ApplicationStatus.DRAFT
    assert draft.docs_state == DocsState.NONE
    # Draft snapshot copies the Job's identity + resolved apply target.
    assert (draft.company, draft.role) == (job.company, job.role)
    assert draft.external_url == job.url

    again = await get_or_create_draft(session, user_id=1, job_id=job.id, settings=settings)
    assert again.id == draft.id  # idempotent per (user, job)

    events = await _events(session, AppEventKind.STATUS_CHANGE)
    assert len(events) == 1  # second call emits nothing
    assert events[0].payload == {
        "from": None,
        "to": ApplicationStatus.DRAFT.value,
        "trigger": StatusChangeTrigger.DRAFT_CREATION.value,
    }


@pytest.mark.asyncio
async def test_queue_auto_apply_flips_job_stamps_and_emits(session):
    job = await _seed_job(session)
    settings = await _seed_settings(session)

    draft = await queue_auto_apply(session, user_id=1, job_id=job.id, settings=settings)

    refreshed = (await session.exec(select(Job).where(Job.id == job.id))).one()
    assert refreshed.queue_state == JobQueueState.QUEUED_FOR_AUTO_APPLY
    blob = (draft.submission_artifacts or {}).get("auto_apply") or {}
    assert blob.get("queued_at")

    events = await _events(session, AppEventKind.STATUS_CHANGE)
    triggers = [e.payload.get("trigger") for e in events]
    assert StatusChangeTrigger.AUTO_APPLY_QUEUED.value in triggers


@pytest.mark.asyncio
async def test_discard_draft_closes_soft_deletes_and_unqueues(session):
    job = await _seed_job(session)
    settings = await _seed_settings(session)
    draft = await queue_auto_apply(session, user_id=1, job_id=job.id, settings=settings)

    result = await discard_draft(session, draft.id)

    assert result.status == ApplicationStatus.CLOSED
    assert result.closed_reason == ClosedReason.WITHDRAWN_BY_ME
    assert result.deleted_at is not None
    refreshed = (await session.exec(select(Job).where(Job.id == job.id))).one()
    assert refreshed.queue_state == JobQueueState.SAVED  # pulled back out of the queue

    events = await _events(session, AppEventKind.STATUS_CHANGE)
    discard_events = [
        e for e in events if e.payload.get("trigger") == StatusChangeTrigger.DISCARD.value
    ]
    assert len(discard_events) == 1
    assert discard_events[0].payload["closed_reason"] == ClosedReason.WITHDRAWN_BY_ME.value


@pytest.mark.asyncio
async def test_discard_non_draft_raises(session):
    app = _make_app(status=ApplicationStatus.APPLIED, applied_at=_NOW)
    session.add(app)
    await session.flush()
    with pytest.raises(IllegalStateTransition):
        await discard_draft(session, app.id)


# ── process_auto_apply_queue characterization ───────────────────────────


async def _queued_draft(session, *, docs_state=DocsState.READY, job_kw=None, app_kw=None):
    job = await _seed_job(
        session, **{"queue_state": JobQueueState.QUEUED_FOR_AUTO_APPLY, **(job_kw or {})}
    )
    app = _make_app(job_id=job.id, docs_state=docs_state, **(app_kw or {}))
    session.add(app)
    await session.flush()
    return job, app


def _submit_ok():
    return AsyncMock(return_value=SimpleNamespace(status=ApplicationStatus.APPLIED))


@pytest.mark.asyncio
async def test_queue_generates_docs_then_submits(session):
    """docs NONE → cron generates the bundle, stamps docs_ready_at, submits,
    stamps submitted_at."""
    await _seed_settings(session, auto_apply_enabled=True, auto_apply_score_threshold=0.5)
    job, app = await _queued_draft(session, docs_state=DocsState.NONE)

    async def fake_generate(sess, application, *, settings, job=None):
        application.docs_state = DocsState.READY
        return SimpleNamespace(skipped_reason=None, degraded=False)

    with (
        patch("services.generation.generate_bundle", new=fake_generate),
        patch("services.applications.submit_draft", new=_submit_ok()),
    ):
        result = await process_auto_apply_queue(session)

    assert (result.processed, result.docs_generated, result.submitted, result.failed) == (
        1,
        1,
        1,
        0,
    )
    blob = (app.submission_artifacts or {}).get("auto_apply") or {}
    assert blob.get("docs_ready_at")
    assert blob.get("submitted_at")


@pytest.mark.asyncio
async def test_queue_cost_capped_generation_counts_skip(session):
    await _seed_settings(session, auto_apply_enabled=True, auto_apply_score_threshold=0.5)
    await _queued_draft(session, docs_state=DocsState.NONE)

    async def capped(sess, application, *, settings, job=None):
        return SimpleNamespace(skipped_reason="cost_cap_reached", degraded=False)

    with patch("services.generation.generate_bundle", new=capped):
        result = await process_auto_apply_queue(session)

    assert result.skipped_by_cap == 1
    assert result.submitted == 0


@pytest.mark.asyncio
async def test_queue_generating_docs_waits_for_next_tick(session):
    await _seed_settings(session, auto_apply_enabled=True)
    job, _ = await _queued_draft(session, docs_state=DocsState.GENERATING)
    result = await process_auto_apply_queue(session)
    assert result.processed == 1
    assert (result.submitted, result.failed, result.handed_to_user) == (0, 0, 0)
    refreshed = (await session.exec(select(Job).where(Job.id == job.id))).one()
    assert refreshed.queue_state == JobQueueState.QUEUED_FOR_AUTO_APPLY  # still queued


@pytest.mark.asyncio
async def test_queue_disabled_hands_to_user_with_reason(session):
    await _seed_settings(session, auto_apply_enabled=False)
    job, app = await _queued_draft(session)

    result = await process_auto_apply_queue(session)

    assert result.handed_to_user == 1
    refreshed = (await session.exec(select(Job).where(Job.id == job.id))).one()
    assert refreshed.queue_state == JobQueueState.READY_TO_SUBMIT
    blob = (app.submission_artifacts or {}).get("auto_apply") or {}
    assert "auto-apply is off" in (blob.get("needs_you_reason") or "")
    handoffs = await _events(session, AppEventKind.AUTO_APPLY_QUEUED)
    assert any(e.payload.get("trigger") == "handed_to_user" for e in handoffs)


@pytest.mark.asyncio
async def test_queue_unsupported_board_hands_to_user(session):
    await _seed_settings(session, auto_apply_enabled=True, auto_apply_score_threshold=0.5)
    job, app = await _queued_draft(
        session,
        job_kw={"board": ApplicationBoard.WORKDAY},
        app_kw={"board": ApplicationBoard.WORKDAY},
    )
    result = await process_auto_apply_queue(session)
    assert result.handed_to_user == 1
    refreshed = (await session.exec(select(Job).where(Job.id == job.id))).one()
    assert refreshed.queue_state == JobQueueState.READY_TO_SUBMIT
    blob = (app.submission_artifacts or {}).get("auto_apply") or {}
    assert "no auto-submit adapter" in (blob.get("needs_you_reason") or "")


@pytest.mark.asyncio
async def test_queue_score_drift_reverts_to_saved(session):
    """Score drifted below the live threshold between queue + dispatch →
    pulled out of the queue, nothing submitted."""
    await _seed_settings(session, auto_apply_enabled=True, auto_apply_score_threshold=0.8)
    job, _ = await _queued_draft(session, job_kw={"score": 0.6})

    submit = _submit_ok()
    with patch("services.applications.submit_draft", new=submit):
        result = await process_auto_apply_queue(session)

    submit.assert_not_awaited()
    assert (result.submitted, result.failed) == (0, 0)
    refreshed = (await session.exec(select(Job).where(Job.id == job.id))).one()
    assert refreshed.queue_state == JobQueueState.SAVED


@pytest.mark.asyncio
async def test_queue_daily_cap_skips(session):
    """Cap=1 with one non-DRAFT application applied today → skipped_by_cap,
    job stays queued (real COUNT query against sqlite)."""
    await _seed_settings(
        session,
        auto_apply_enabled=True,
        auto_apply_score_threshold=0.5,
        auto_apply_daily_cap=1,
    )
    applied_today = _make_app(
        status=ApplicationStatus.APPLIED,
        applied_at=datetime.now(UTC) - timedelta(minutes=5),
        company="Other",
    )
    session.add(applied_today)
    job, _ = await _queued_draft(session)

    submit = _submit_ok()
    with patch("services.applications.submit_draft", new=submit):
        result = await process_auto_apply_queue(session)

    submit.assert_not_awaited()
    assert result.skipped_by_cap == 1
    refreshed = (await session.exec(select(Job).where(Job.id == job.id))).one()
    assert refreshed.queue_state == JobQueueState.QUEUED_FOR_AUTO_APPLY


@pytest.mark.asyncio
async def test_queue_visa_blocked_unqueues_and_emits(session):
    """Profile NEEDED_NOW × job US_CITIZEN_ONLY → validate_submittable's
    sponsorship gate pulls the job out of the queue + emits
    AUTO_APPLY_VISA_BLOCKED (the plan-78 tight-loop fix)."""
    await _seed_profile(session, visa_sponsorship_needed=VisaSponsorship.NEEDED_NOW)
    await _seed_settings(session, auto_apply_enabled=True, auto_apply_score_threshold=0.5)
    job, _ = await _queued_draft(
        session, job_kw={"visa_restrictions": VisaRestriction.US_CITIZEN_ONLY}
    )

    submit = _submit_ok()
    with patch("services.applications.submit_draft", new=submit):
        result = await process_auto_apply_queue(session)

    submit.assert_not_awaited()
    assert (result.submitted, result.failed) == (0, 0)
    refreshed = (await session.exec(select(Job).where(Job.id == job.id))).one()
    assert refreshed.queue_state == JobQueueState.SAVED
    blocked = await _events(session, AppEventKind.AUTO_APPLY_VISA_BLOCKED)
    assert len(blocked) == 1


@pytest.mark.asyncio
async def test_queue_submission_failure_hands_to_user_with_message(session):
    """submit_draft returns a still-DRAFT app → failed + handed over with the
    recorded failure message."""
    await _seed_settings(session, auto_apply_enabled=True, auto_apply_score_threshold=0.5)
    job, app = await _queued_draft(session)
    app.submission_artifacts = {"last_failure": {"kind": "captcha", "message": "captcha wall"}}
    session.add(app)
    await session.flush()

    submit = AsyncMock(return_value=SimpleNamespace(status=ApplicationStatus.DRAFT))
    with patch("services.applications.submit_draft", new=submit):
        result = await process_auto_apply_queue(session)

    assert (result.failed, result.handed_to_user) == (1, 1)
    refreshed = (await session.exec(select(Job).where(Job.id == job.id))).one()
    assert refreshed.queue_state == JobQueueState.READY_TO_SUBMIT
    blob = (app.submission_artifacts or {}).get("auto_apply") or {}
    assert "captcha wall" in (blob.get("needs_you_reason") or "")


@pytest.mark.asyncio
async def test_queue_ignores_other_users_when_scoped(session):
    """user_id scoping: another user's queued draft is untouched."""
    session.add(User(id=2, email="other@t.test", password_hash="x"))
    await session.flush()
    await _seed_settings(session, auto_apply_enabled=True, auto_apply_score_threshold=0.5)
    job2 = await _seed_job(
        session, user_id=2, company="Other", queue_state=JobQueueState.QUEUED_FOR_AUTO_APPLY
    )
    app2 = _make_app(user_id=2, job_id=job2.id, docs_state=DocsState.READY, company="Other")
    session.add(app2)
    await session.flush()

    result = await process_auto_apply_queue(session, user_id=1)
    assert result.processed == 0


# Sanity: the module-under-test import seam used by the queue patches above.
def test_patch_seams_exist():
    assert hasattr(application_service, "submit_draft")
    import services.generation as bg

    assert hasattr(bg, "generate_bundle")
