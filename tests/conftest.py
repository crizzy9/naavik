"""Test configuration. Inserts `src/` onto sys.path so tests can import as the
runtime does (`from main import app`, `from ui.templates_setup import templates`).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Switch CWD to the repo root so relative paths in the FastAPI app resolve
# (e.g. `Jinja2Templates(directory="src/ui/templates")`).
os.chdir(Path(__file__).resolve().parent.parent)

# Allow tests to import + boot the FastAPI app without an explicit SECRET_KEY.
# Mirrors the `nix run .#dev` orchestrator's debug bypass.
os.environ.setdefault("NAAVIK_DEBUG", "1")

import pytest  # noqa: E402


class _NoopSession:
    """In-memory session stub.

    Plan 69 (`0.3.3.12`) rewired every route + ctx-builder to consume an
    `AsyncSession` through `Depends(get_session)`. The legacy tests below
    don't seed Postgres — they relied on the in-memory `db.sample_data`
    accessors. The conftest fixture `_patch_services_to_sample_data` wraps
    each service-layer function so it pulls from `sd.*` shadow rows; the
    handler-injected `session` argument is this noop. Tests that exercise
    real DB behavior override `dependency_overrides[get_session]` per-test
    (pattern documented in `tests/test_pages.py:test_settings_all_seven_tabs`).
    """

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def flush(self) -> None:
        return None

    async def refresh(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def add(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def delete(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    async def exec(self, *_args: Any, **_kwargs: Any) -> Any:
        # Routes that call `session.exec` directly bypass the patched
        # service layer; provide an empty-result stub so the call surface
        # doesn't 500. Tests asserting the SELECT result must monkeypatch
        # the underlying service or `session.exec` directly.
        class _EmptyResult:
            def one_or_none(self_):  # noqa: N805
                return None

            def all(self_):  # noqa: N805
                return []

            def one(self_):  # noqa: N805
                return None

        return _EmptyResult()


@pytest.fixture(autouse=True)
def _disable_background_generation():
    """Background bundle generation opens its own `db.session.async_session`,
    which test fixtures don't override — a spawned task would write to (or
    hang on) the operator's real DB. Off for every test; generation_dispatch
    unit tests exercise `_run_generation` directly."""
    from services.generation import dispatch as generation_dispatch

    generation_dispatch.enabled = False
    yield
    generation_dispatch.enabled = True


@pytest.fixture(autouse=True)
def _restore_sample_data(request):
    """Snapshot/restore the mutable `sample_data` collections around each
    shim-tier test (plan 91 Phase 0.4).

    The fake service helpers (`sd._append_manual_application`, `_create_draft`,
    `_apply_status_override`, `_record_screener_answer`, queue-state flips, …)
    mutate module-level lists **in place**, so without a restore the pass/fail
    of one test can depend on rows another test left behind. A handful of files
    hand-rolled this (`test_stub_endpoints.py`, `test_draft_lifecycle.py`);
    this generalizes it to every shim-tier test.

    Deep-copies capture in-place row-field edits (status/queue_state/answer),
    not just list membership. Gated on the marker — the sqlite/live tiers use
    real sessions and never touch `sample_data` mutably, so they skip the cost.
    A file's own restore fixture nests harmlessly inside this one.
    """
    if not list(request.node.iter_markers("uses_sample_data_shims")):
        yield
        return
    from db import sample_data as sd

    _MUTABLE = (
        "APPLICATIONS",
        "JOBS",
        "OUTREACH_MESSAGES",
        "APP_EVENTS",
        "GENERATED_DOCUMENTS",
        "SCREENER_ANSWERS",
        "BULLETS",
        "CONTACTS",
    )
    snapshots = {
        name: [row.model_copy(deep=True) for row in getattr(sd, name)] for name in _MUTABLE
    }
    yield
    for name, snapshot in snapshots.items():
        collection = getattr(sd, name)
        collection.clear()
        collection.extend(snapshot)


@pytest.fixture(autouse=True)
def _patch_services_to_sample_data(request, monkeypatch):
    """Make route → service-layer reads transparent to the legacy fixtures.

    Plan 69 (`0.3.3.12`) moved routes + ctx-builders off the in-memory
    `db.sample_data` accessors onto the live service layer. Tests written
    before plan 69 expect the same in-memory data to surface in rendered
    pages. This fixture monkey-patches each service function used by the
    rewired surfaces to return the corresponding `sd.*` shadow row, and
    overrides `get_session` globally so routes inject a noop session.

    Plan 87 (`0.4.5.03`) inverted the default from autouse + opt-out to
    opt-in via `@pytest.mark.uses_sample_data_shims` at the module / class
    / function level. The fixture remains `autouse=True` so pytest still
    discovers it, but the body is a no-op unless the marker is present.
    Files that exercise the service layer directly (real sqlite or
    `NAAVIK_LIVE_DB=1` Postgres) simply omit the marker.

    Per-test overrides (`app.dependency_overrides[get_session] = ...` or
    explicit `monkeypatch.setattr(service, "fn", ...)` calls in the test
    body) take precedence — FastAPI's override dict is last-write-wins
    and pytest's monkeypatch is per-test.
    """
    if not list(request.node.iter_markers("uses_sample_data_shims")):
        yield
        return
    from db import sample_data as sd
    from db.session import get_session
    from main import app
    from models.enums import ApplicationStatus, EmailClassification, JobQueueState
    from services import (
        applications,
        email,
        llm_tracker,
        overview_service,
    )
    from services import (
        auth as user_service,
    )
    from services import (
        jobs as job_service,
    )
    from services import (
        outreach as contact_tracker,
    )
    from services import (
        outreach as outreach_service,
    )
    from services import (
        profile as profile_service,
    )
    from services import (
        settings as settings_service,
    )

    async def _fake_get_session():
        yield _NoopSession()

    app.dependency_overrides[get_session] = _fake_get_session

    # P6.4 — the model dropdown now asks provider list-models APIs at
    # request time; tests must never hit the network. Pin to the static
    # fallback catalog.
    from services.settings import llm_models

    async def _static_models(provider_id: str) -> list[str]:
        return list(llm_models.FALLBACK_MODELS.get(provider_id, []))

    monkeypatch.setattr(llm_models, "list_models", _static_models)

    # ── profile_service ─────────────────────────────────────────────────
    async def _get_profile(_session, _user_id):
        return sd.PROFILE

    async def _list_experiences(_session, _user_id):
        return sorted(sd.EXPERIENCES, key=lambda e: e.order_index)

    async def _get_bullets_for_experience(_session, experience_id):
        return sorted(
            [b for b in sd.BULLETS if b.experience_id == experience_id],
            key=lambda b: b.order_index,
        )

    async def _get_bullet(_session, bullet_id):
        return next((b for b in sd.BULLETS if b.id == bullet_id), None)

    async def _get_experience(_session, experience_id):
        return next((e for e in sd.EXPERIENCES if e.id == experience_id), None)

    _real_owns_bullet = profile_service.owns_bullet

    async def _owns_bullet(_session, *, bullet_id, user_id):
        # Route tests inject a `_NoopSession` — resolve ownership via the sd
        # bullet → experience → profile chain. Files that carry the shim marker
        # but seed their OWN sqlite and call owns_bullet directly (e.g.
        # test_hardening_pass) pass a real AsyncSession whose bullet ids collide
        # with sd's, so those must hit the real query. (plan 91 Phase 1.2 wired
        # owns_bullet into the bullet-fragment deps.)
        if not isinstance(_session, _NoopSession):
            return await _real_owns_bullet(_session, bullet_id=bullet_id, user_id=user_id)
        bullet = next((b for b in sd.BULLETS if b.id == bullet_id), None)
        if bullet is None:
            return False
        experience = next((e for e in sd.EXPERIENCES if e.id == bullet.experience_id), None)
        if experience is None:
            return False
        return experience.profile_id == sd.PROFILE.id and sd.PROFILE.user_id == user_id

    async def _list_skills(_session, _user_id):
        return sorted(sd.SKILLS, key=lambda s: s.order_index)

    async def _list_educations(_session, _user_id):
        return list(sd.EDUCATIONS)

    async def _list_projects(_session, _user_id):
        return list(sd.PROJECTS)

    async def _list_certifications(_session, _user_id):
        return list(sd.CERTIFICATIONS)

    async def _list_all_bullets(_session, _user_id):
        return sorted(sd.BULLETS, key=lambda b: b.order_index)

    async def _get_score_history(_session, _user_id):
        # Plan 73 (0.3.2.03): expose the seeded sparkline fixture to legacy
        # tests that exercise the Profile page; tests that monkeypatch this
        # per-test (e.g. the empty-state assertion) take precedence.
        return dict(getattr(sd.PROFILE, "score_history", {}) or {})

    monkeypatch.setattr(profile_service, "get_profile", _get_profile)
    monkeypatch.setattr(profile_service, "get_score_history", _get_score_history)
    monkeypatch.setattr(profile_service, "list_experiences", _list_experiences)
    monkeypatch.setattr(profile_service, "get_bullets_for_experience", _get_bullets_for_experience)
    monkeypatch.setattr(profile_service, "get_bullet", _get_bullet)
    monkeypatch.setattr(profile_service, "owns_bullet", _owns_bullet)
    monkeypatch.setattr(profile_service, "get_experience", _get_experience)
    monkeypatch.setattr(profile_service, "list_skills", _list_skills)
    monkeypatch.setattr(profile_service, "list_educations", _list_educations)
    monkeypatch.setattr(profile_service, "list_projects", _list_projects)
    monkeypatch.setattr(profile_service, "list_certifications", _list_certifications)
    monkeypatch.setattr(profile_service, "list_all_bullets", _list_all_bullets)

    # ── job_service ─────────────────────────────────────────────────────
    async def _get_job(_session, job_id):
        return next((j for j in sd.JOBS if j.id == job_id), None)

    async def _list_jobs(_session, *, user_id, filters=None, page=0, page_size=50):
        result = [j for j in sd.JOBS if getattr(j, "user_id", 1) == user_id]
        result = [j for j in result if getattr(j, "deleted_at", None) is None]
        if filters is not None:
            if not getattr(filters, "include_duplicates", False):
                result = [j for j in result if getattr(j, "duplicate_of_id", None) is None]
            if filters.company is not None:
                result = [j for j in result if j.company == filters.company]
            if filters.source is not None:
                result = [j for j in result if j.source == filters.source]
            if filters.visa is not None:
                result = [j for j in result if j.visa_restrictions == filters.visa]
            if filters.remote_only:
                from models.enums import RemotePolicy

                result = [j for j in result if j.remote_policy == RemotePolicy.REMOTE]
            if filters.seniority is not None:
                result = [j for j in result if j.seniority_level == filters.seniority]
            if filters.queue_state is not None:
                result = [j for j in result if j.queue_state == filters.queue_state]
            if filters.score_min > 0.0:
                result = [j for j in result if j.score >= filters.score_min]
        result = sorted(result, key=lambda j: (j.score, j.found_at), reverse=True)
        start = page * page_size
        return result[start : start + page_size]

    async def _list_jobs_by_queue_state(_session, *, user_id, state):
        return [
            j for j in sd.JOBS if getattr(j, "user_id", 1) == user_id and j.queue_state == state
        ]

    async def _auto_apply_queue(_session, *, user_id):
        # Match the service-layer behavior: returns Jobs queued for auto-apply.
        return [
            j
            for j in sd.JOBS
            if getattr(j, "user_id", 1) == user_id
            and j.queue_state == JobQueueState.QUEUED_FOR_AUTO_APPLY
        ]

    async def _set_queue_state(_session, job_id, *, user_id, state):
        job = next((j for j in sd.JOBS if j.id == job_id), None)
        if job is None:
            raise PermissionError(f"job {job_id} not found")
        if getattr(job, "user_id", 1) != user_id:
            raise PermissionError(f"job {job_id} does not belong to user {user_id}")
        job.queue_state = state
        return job

    async def _list_recent_scrape_runs(_session, *, user_id, limit=50):
        return list(sd.JOB_SCRAPE_RUNS)[:limit]

    async def _get_scrape_run(_session, scrape_run_id):
        return next((r for r in sd.JOB_SCRAPE_RUNS if r.id == scrape_run_id), None)

    async def _list_recent_scrape_runs_by_source(_session, *, user_id):
        out: dict = {}
        for r in sd.JOB_SCRAPE_RUNS:
            existing = out.get(r.source)
            if existing is None or r.started_at > existing.started_at:
                out[r.source] = r
        return out

    monkeypatch.setattr(job_service, "get_job", _get_job)
    monkeypatch.setattr(job_service, "list_jobs", _list_jobs)
    monkeypatch.setattr(job_service, "list_jobs_by_queue_state", _list_jobs_by_queue_state)
    monkeypatch.setattr(job_service, "auto_apply_queue", _auto_apply_queue)

    async def _count_jobs_in_queue_state(_session, *, user_id, state):
        return len(await _list_jobs_by_queue_state(_session, user_id=user_id, state=state))

    def _as_aware(dt):
        from datetime import UTC as _UTC

        return dt if dt.tzinfo is not None else dt.replace(tzinfo=_UTC)

    async def _sum_listings_scanned_since(_session, *, user_id, since):
        return sum(
            int(getattr(r, "listings_returned", 0) or 0)
            for r in sd.JOB_SCRAPE_RUNS
            if r.started_at is not None and _as_aware(r.started_at) >= _as_aware(since)
        )

    monkeypatch.setattr(job_service, "set_queue_state", _set_queue_state)
    monkeypatch.setattr(job_service, "list_recent_scrape_runs", _list_recent_scrape_runs)
    monkeypatch.setattr(job_service, "get_scrape_run", _get_scrape_run)
    monkeypatch.setattr(
        job_service, "list_recent_scrape_runs_by_source", _list_recent_scrape_runs_by_source
    )
    monkeypatch.setattr(job_service, "count_jobs_in_queue_state", _count_jobs_in_queue_state)
    monkeypatch.setattr(job_service, "sum_listings_scanned_since", _sum_listings_scanned_since)

    # ── application_service ─────────────────────────────────────────────
    async def _get_application(_session, application_id):
        return next((a for a in sd.APPLICATIONS if a.id == application_id), None)

    async def _get_application_for_job(_session, *, user_id, job_id):
        return next(
            (
                a
                for a in sd.APPLICATIONS
                if a.user_id == user_id and a.job_id == job_id and a.deleted_at is None
            ),
            None,
        )

    async def _stuck_drafts(_session, *, user_id):
        return [
            a
            for a in sd.APPLICATIONS
            if a.user_id == user_id
            and a.status == ApplicationStatus.DRAFT
            and a.submission_artifacts
            and a.submission_artifacts.get("last_failure")
            and a.deleted_at is None
        ]

    _TRACKING_VISIBLE = {
        ApplicationStatus.APPLIED,
        ApplicationStatus.RECRUITER_SCREEN,
        ApplicationStatus.ONSITE_LOOP,
        ApplicationStatus.OFFER,
    }

    async def _list_visible_in_tracking(_session, user_id):
        return [
            a
            for a in sd.APPLICATIONS
            if a.user_id == user_id and a.status in _TRACKING_VISIBLE and a.deleted_at is None
        ]

    async def _list_by_status(_session, user_id, status):
        return [
            a
            for a in sd.APPLICATIONS
            if a.user_id == user_id and a.status == status and a.deleted_at is None
        ]

    async def _list_in_followup(_session, user_id):
        from models.enums import RecruiterState

        followup_states = {RecruiterState.SILENT, RecruiterState.STALLED}
        return [
            a
            for a in sd.APPLICATIONS
            if a.user_id == user_id
            and a.recruiter_state in followup_states
            and a.status not in {ApplicationStatus.DRAFT, ApplicationStatus.CLOSED}
            and a.deleted_at is None
        ]

    async def _list_closed(_session, user_id):
        return await _list_by_status(_session, user_id, ApplicationStatus.CLOSED)

    async def _list_drafts(_session, user_id):
        return await _list_by_status(_session, user_id, ApplicationStatus.DRAFT)

    async def _list_applications(_session, *, user_id, statuses=None, include_deleted=False):
        result = [a for a in sd.APPLICATIONS if a.user_id == user_id]
        if not include_deleted:
            result = [a for a in result if a.deleted_at is None]
        if statuses is not None:
            result = [a for a in result if a.status in statuses]
        return result

    async def _list_documents_for(_session, application_id):
        return sorted(
            [
                d
                for d in sd.GENERATED_DOCUMENTS
                if d.application_id == application_id and d.error is None
            ],
            key=lambda d: d.compiled_at,
            reverse=True,
        )

    async def _list_screener_answers_for(_session, application_id):
        return sorted(
            [s for s in sd.SCREENER_ANSWERS if s.application_id == application_id],
            key=lambda s: s.order_index,
        )

    async def _get_screener_answer(_session, answer_id, *, owner_user_id=None):
        return next((s for s in sd.SCREENER_ANSWERS if s.id == answer_id), None)

    async def _count_unreviewed_required_screeners(_session, application_id):
        return sum(
            1
            for s in sd.SCREENER_ANSWERS
            if s.application_id == application_id and s.required and s.reviewed_at is None
        )

    async def _list_events_for(_session, application_id, *, limit=50):
        return sorted(
            [e for e in sd.APP_EVENTS if e.application_id == application_id],
            key=lambda e: e.occurred_at,
            reverse=True,
        )[:limit]

    async def _create_manual(
        _session,
        *,
        user_id,
        company,
        role,
        team=None,
        location=None,
        salary_min=None,
        salary_max=None,
        notes=None,
    ):
        return await sd._append_manual_application(
            company=company,
            role=role,
            team=team,
            location=location,
            salary_min=salary_min,
            salary_max=salary_max,
            notes=notes,
        )

    async def _get_or_create_draft(_session, *, user_id, job_id, settings=None):
        existing = next(
            (
                a
                for a in sd.APPLICATIONS
                if a.user_id == user_id
                and a.job_id == job_id
                and a.status == ApplicationStatus.DRAFT
                and a.deleted_at is None
            ),
            None,
        )
        if existing is not None:
            return existing
        return await sd._create_draft(user_id, job_id)

    async def _queue_auto_apply(_session, *, user_id, job_id, settings=None):
        draft = await _get_or_create_draft(
            _session, user_id=user_id, job_id=job_id, settings=settings
        )
        job = next((j for j in sd.JOBS if j.id == job_id), None)
        if job is not None:
            job.queue_state = JobQueueState.QUEUED_FOR_AUTO_APPLY
        return draft

    async def _record_draft_failure(_session, application_id, *, kind, message=""):
        return await sd._apply_failure_to_draft(application_id, kind, message)

    async def _update_status(
        _session, application_id, target_status, *, trigger="manual", closed_reason=None
    ):
        return await sd._apply_status_override(
            application_id, target_status, trigger=trigger, closed_reason=closed_reason
        )

    async def _record_screener_answer(_session, answer_id, answer, *, owner_user_id=None):
        return await sd._record_screener_answer(answer_id, answer)

    async def _aggregate_submission_failures(_session, *, user_id, since_days=30):
        # Return empty for tests that don't override; legitimate tests
        # asserting failure aggregates override this per-test.
        return []

    async def _count_applied_since(_session, *, user_id, since):
        return len(
            [
                a
                for a in sd.APPLICATIONS
                if getattr(a, "user_id", 1) == user_id
                and getattr(a, "applied_at", None) is not None
                and _as_aware(a.applied_at) >= _as_aware(since)
            ]
        )

    monkeypatch.setattr(applications, "count_applied_since", _count_applied_since)
    monkeypatch.setattr(applications, "get_application", _get_application)
    monkeypatch.setattr(applications, "get_application_for_job", _get_application_for_job)
    monkeypatch.setattr(applications, "stuck_drafts", _stuck_drafts)
    monkeypatch.setattr(applications, "list_visible_in_tracking", _list_visible_in_tracking)
    monkeypatch.setattr(applications, "list_by_status", _list_by_status)
    monkeypatch.setattr(applications, "list_in_followup", _list_in_followup)
    monkeypatch.setattr(applications, "list_closed", _list_closed)
    monkeypatch.setattr(applications, "list_drafts", _list_drafts)
    monkeypatch.setattr(applications, "list_applications", _list_applications)
    monkeypatch.setattr(applications, "list_documents_for", _list_documents_for)
    monkeypatch.setattr(applications, "list_screener_answers_for", _list_screener_answers_for)
    monkeypatch.setattr(applications, "get_screener_answer", _get_screener_answer)
    monkeypatch.setattr(
        applications,
        "count_unreviewed_required_screeners",
        _count_unreviewed_required_screeners,
    )
    monkeypatch.setattr(applications, "list_events_for", _list_events_for)
    monkeypatch.setattr(applications, "create_manual", _create_manual)
    monkeypatch.setattr(applications, "get_or_create_draft", _get_or_create_draft)
    monkeypatch.setattr(applications, "queue_auto_apply", _queue_auto_apply)
    monkeypatch.setattr(applications, "record_draft_failure", _record_draft_failure)
    monkeypatch.setattr(applications, "update_status", _update_status)
    monkeypatch.setattr(applications, "record_screener_answer", _record_screener_answer)
    monkeypatch.setattr(
        applications, "aggregate_submission_failures", _aggregate_submission_failures
    )

    # ── contact_tracker ─────────────────────────────────────────────────
    async def _get_contact(_session, contact_id):
        return next((c for c in sd.CONTACTS if c.id == contact_id), None)

    async def _list_contacts(_session, user_id):
        return [c for c in sd.CONTACTS if c.user_id == user_id and c.deleted_at is None]

    async def _list_contacts_for_company(_session, *, user_id, company):
        return [
            c
            for c in sd.CONTACTS
            if c.user_id == user_id and c.company == company and c.deleted_at is None
        ]

    async def _list_contacts_for_application(_session, application_id):
        return await sd.contacts_for_application(application_id)

    monkeypatch.setattr(contact_tracker, "get_contact", _get_contact)
    monkeypatch.setattr(contact_tracker, "list_contacts", _list_contacts)
    monkeypatch.setattr(contact_tracker, "list_contacts_for_company", _list_contacts_for_company)
    monkeypatch.setattr(
        contact_tracker, "list_contacts_for_application", _list_contacts_for_application
    )

    # ── outreach_service ────────────────────────────────────────────────
    async def _list_messages_for_contact(_session, contact_id):
        return sorted(
            [m for m in sd.OUTREACH_MESSAGES if m.contact_id == contact_id],
            key=lambda m: m.created_at,
            reverse=True,
        )

    async def _list_messages_for_application(_session, application_id):
        return sorted(
            [m for m in sd.OUTREACH_MESSAGES if m.application_id == application_id],
            key=lambda m: m.created_at,
            reverse=True,
        )

    async def _list_all_messages(_session, user_id):
        return sorted(
            [m for m in sd.OUTREACH_MESSAGES if m.user_id == user_id],
            key=lambda m: m.created_at,
            reverse=True,
        )

    async def _get_message(_session, message_id):
        return next((m for m in sd.OUTREACH_MESSAGES if m.id == message_id), None)

    async def _create_message(
        _session,
        *,
        user_id,
        contact_id,
        application_id=None,
        intent,
        body,
        status,
        channel="linkedin",
    ):
        return await sd._append_outreach_message(
            contact_id,
            application_id,
            intent,
            body,
            status=status,
            channel=channel,
        )

    async def _mark_sent(_session, message_id):
        from datetime import UTC, datetime

        from models.enums import OutreachStatus

        msg = next((m for m in sd.OUTREACH_MESSAGES if m.id == message_id), None)
        if msg is None:
            return None
        msg.status = OutreachStatus.SENT
        msg.sent_at = datetime.now(UTC)
        return msg

    monkeypatch.setattr(outreach_service, "list_messages_for_contact", _list_messages_for_contact)
    monkeypatch.setattr(
        outreach_service, "list_messages_for_application", _list_messages_for_application
    )
    monkeypatch.setattr(outreach_service, "list_all_messages", _list_all_messages)
    monkeypatch.setattr(outreach_service, "get_message", _get_message)
    monkeypatch.setattr(outreach_service, "create_message", _create_message)
    monkeypatch.setattr(outreach_service, "mark_sent", _mark_sent)

    # ── email_service ───────────────────────────────────────────────────
    async def _list_threads(_session, user_id, *, application_id=None, classification=None):
        result = [t for t in sd.EMAIL_THREADS if t.user_id == user_id]
        if application_id is not None:
            result = [t for t in result if t.application_id == application_id]
        if classification is not None:
            result = [t for t in result if t.classification == classification]
        return sorted(result, key=lambda t: t.latest_message_at, reverse=True)

    async def _get_thread(_session, thread_id):
        return next((t for t in sd.EMAIL_THREADS if t.id == thread_id), None)

    async def _list_threads_for_application(_session, application_id):
        return sorted(
            [t for t in sd.EMAIL_THREADS if t.application_id == application_id],
            key=lambda t: t.latest_message_at,
            reverse=True,
        )

    async def _recent_signals(_session, user_id, *, limit=6):
        return sorted(
            [
                t
                for t in sd.EMAIL_THREADS
                if t.user_id == user_id
                and t.classification
                in {
                    EmailClassification.INTERVIEW_REQUEST,
                    EmailClassification.ASSESSMENT,
                    EmailClassification.OFFER,
                    EmailClassification.REJECTION,
                }
            ],
            key=lambda t: t.latest_message_at,
            reverse=True,
        )[:limit]

    monkeypatch.setattr(email, "list_threads", _list_threads)
    monkeypatch.setattr(email, "get_thread", _get_thread)
    monkeypatch.setattr(email, "list_threads_for_application", _list_threads_for_application)
    monkeypatch.setattr(email, "recent_signals", _recent_signals)

    # ── overview_service ────────────────────────────────────────────────
    async def _compute_kpis(_session, user_id, *, window_days=90):
        active = await sd.kpi_active_applications()
        response = await sd.kpi_response_rate_90d()
        onsite = await sd.kpi_onsite_rate_90d()
        offer = await sd.kpi_offer_rate_90d()
        offer_count = sum(1 for a in sd.APPLICATIONS if a.status == ApplicationStatus.OFFER)
        return overview_service.KPISet(
            active_applications=active,
            response_rate=response,
            onsite_rate=onsite,
            offer_rate=offer,
            offer_count=offer_count,
        )

    async def _pipeline_strip_counts(_session, _user_id):
        return await sd.pipeline_strip_counts()

    async def _compose_priority_actions(_session, _user_id, *, limit=8):
        return await sd.priority_actions(limit=limit)

    async def _list_applications_by_status(_session, user_id, status):
        return await _list_by_status(_session, user_id, status)

    monkeypatch.setattr(overview_service, "compute_kpis", _compute_kpis)
    monkeypatch.setattr(overview_service, "pipeline_strip_counts", _pipeline_strip_counts)
    monkeypatch.setattr(overview_service, "compose_priority_actions", _compose_priority_actions)
    monkeypatch.setattr(
        overview_service, "list_applications_by_status", _list_applications_by_status
    )

    # ── settings_service ────────────────────────────────────────────────
    # The shadow `sd.SETTINGS` is a Pydantic BaseModel missing some
    # SQLModel-only fields (`linkedin_keywords`, `indeed_keywords`, etc).
    # Build a real `models.Settings` instance from the shadow payload on
    # each call so any in-test mutation of `sd.SETTINGS` propagates.
    from models import Settings as _SettingsRow

    async def _get_or_create(_session, user_id):
        return _SettingsRow.model_validate(sd.SETTINGS.model_dump())

    async def _compute_premium_cost_projection(_session, *, user_id):
        from services.settings import _PREMIUM_PROJECTION_FALLBACK

        return _PREMIUM_PROJECTION_FALLBACK

    async def _list_recent_generation_traces(_session, *, user_id, limit=20):
        return []

    async def _get_deployment_info(_session, user_id):
        return {
            "mode": "self_hosted",
            "version": "0.4.2",
            "uptime_seconds": 14 * 86400,
            "scheduler_status": "running",
            "data_dir": "~/.naavik/data",
        }

    monkeypatch.setattr(settings_service, "get_or_create", _get_or_create)
    monkeypatch.setattr(
        settings_service, "compute_premium_cost_projection", _compute_premium_cost_projection
    )
    monkeypatch.setattr(
        settings_service, "list_recent_generation_traces", _list_recent_generation_traces
    )
    monkeypatch.setattr(settings_service, "get_deployment_info", _get_deployment_info)

    # ── llm_tracker ─────────────────────────────────────────────────────
    async def _today_cost_usd(_session, *, user_id):
        return 0.0

    async def _recent_usage(_session, *, user_id, days=30):
        return await sd.api_usage_recent(days=days)

    async def _usage_summary(_session, *, user_id, days=30):
        raw = await sd.llm_usage_summary(days=days)
        # `services.llm_tracker.UsageSummary` is a dataclass with
        # month_cost_usd / avg_per_generation_usd / total_tokens / gen_count.
        # `sd.llm_usage_summary` returns a dict with the same keys.
        return llm_tracker.UsageSummary(
            month_cost_usd=raw["month_cost_usd"],
            avg_per_generation_usd=raw["avg_per_generation_usd"],
            total_tokens=int(raw["total_tokens"]),
            gen_count=int(raw["gen_count"]),
        )

    # Plan 74 / 0.3.2.04 — judge-skipped fallback banner helpers. The
    # in-memory sample_data fixtures don't populate `match_breakdown.
    # judge_skipped`, so the autouse default returns no skips. Tests
    # that exercise the banner override via per-test monkeypatch.
    async def _judge_skipped_count_today(_session, *, user_id):
        return 0

    async def _judge_skipped_reasons_today(_session, *, user_id):
        return {}

    monkeypatch.setattr(llm_tracker, "today_cost_usd", _today_cost_usd)
    monkeypatch.setattr(llm_tracker, "recent_usage", _recent_usage)
    monkeypatch.setattr(llm_tracker, "usage_summary", _usage_summary)
    monkeypatch.setattr(llm_tracker, "judge_skipped_count_today", _judge_skipped_count_today)
    monkeypatch.setattr(llm_tracker, "judge_skipped_reasons_today", _judge_skipped_reasons_today)

    # ── user_service ────────────────────────────────────────────────────
    async def _get_user(_session, user_id):
        return sd.USER if sd.USER.id == user_id else None

    monkeypatch.setattr(user_service, "get_user", _get_user)

    yield

    app.dependency_overrides.pop(get_session, None)


# ── Shared client / auth / CSRF fixtures (plan 91 Phase 0.3) ──────────────
# 79 test files self-roll `TestClient` + fake-session + CSRF boilerplate. These
# provide one shared trio so route restructuring is a single edit. A module
# that defines its own same-name fixture (e.g. `client`) overrides these — the
# existing self-rolled fixtures keep winning locally, so nothing breaks.

_SHARED_CSRF_TOKEN = "csrf-shared-token-aaaaaaaaaaaaaaaaaaaaaaaaaaaa"


@pytest.fixture
def csrf_token() -> str:
    return _SHARED_CSRF_TOKEN


@pytest.fixture
def csrf_headers() -> dict[str, str]:
    """`X-CSRF-Token` header matching `auth_cookies` for double-submit POSTs.
    HTMX injects this globally in prod (`base.html`); tests thread it."""
    return {"X-CSRF-Token": _SHARED_CSRF_TOKEN}


@pytest.fixture
def auth_cookies() -> dict[str, str]:
    """Debug fake-session cookie + matching CSRF cookie. `require_authed_session`
    accepts `fake-1` only under `NAAVIK_DEBUG=1` (set in this conftest)."""
    return {"naavik_session": "fake-1", "naavik_csrf": _SHARED_CSRF_TOKEN}


@pytest.fixture
def client():
    """Plain `TestClient` — no auth cookies. Use for unauthenticated-path
    assertions or seed cookies yourself."""
    from fastapi.testclient import TestClient

    from main import app

    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture
def authed_client(auth_cookies):
    """`TestClient` pre-seeded with the debug fake-session + CSRF cookies — the
    dominant pattern across the suite."""
    from fastapi.testclient import TestClient

    from main import app

    test_client = TestClient(app, raise_server_exceptions=True)
    test_client.cookies.update(auth_cookies)
    return test_client
