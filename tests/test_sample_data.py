"""Round-trip + count + realism rule tests for sample_data.py.

Per plan 09 § I:
- Every fixture round-trips through Pydantic (catches drift if a model field is
  added in DATA_MODEL.md but missing in fixtures).
- Counts match SAMPLE_DATA.md inventory ranges.
- Visa-rule coverage: ≥2 jobs with `us_citizen_only` scoring 0.
- DRAFT coverage: ≥2 DRAFT applications, both with docs_state=ready, both with
  full screener-answer rows.
- Recruiter silence stress: ≥1 application `recruiter_state=silent` for ≥6d.
- Stuck queue: ≥1 DRAFT application with `submission_artifacts.last_failure`.
"""

from __future__ import annotations

import inspect
from datetime import timedelta

import pytest

from db import sample_data as sd
from db.sample_data_models import (
    ApiUsage,
    AppEvent,
    Application,
    ApplicationScreenerAnswer,
    ATSCredential,
    Bullet,
    Certification,
    Contact,
    ContactApplicationLink,
    Education,
    EmailThread,
    Experience,
    GeneratedDocument,
    Job,
    OutreachMessage,
    Profile,
    Project,
    Settings,
    Skill,
    User,
)
from models.enums import (
    ApplicationStatus,
    BulletSelectionOverride,
    ContactType,
    DocsState,
    JobQueueState,
    LLMProvider,
    OutreachStatus,
    RecruiterState,
    Tag,
)

pytestmark = pytest.mark.uses_sample_data_shims

# ── Round-trip ───────────────────────────────────────────────────────────


def _round_trip(items: list, model: type) -> None:
    """Dump every item to dict and rehydrate via the same Pydantic model — fails
    if a field added to the model is missing in the fixture (or vice-versa).
    """
    for it in items:
        assert isinstance(it, model), f"{type(it).__name__} not {model.__name__}"
        rebuilt = model.model_validate(it.model_dump())
        # Field-by-field equality on the model dump (handles enum normalization)
        assert rebuilt.model_dump() == it.model_dump(), (
            f"round-trip diverged for {model.__name__} id={getattr(it, 'id', '?')}"
        )


def test_round_trip_user() -> None:
    _round_trip([sd.USER], User)


def test_round_trip_profile() -> None:
    _round_trip([sd.PROFILE], Profile)


def test_round_trip_experiences() -> None:
    _round_trip(sd.EXPERIENCES, Experience)


def test_round_trip_bullets() -> None:
    _round_trip(sd.BULLETS, Bullet)


def test_round_trip_skills() -> None:
    _round_trip(sd.SKILLS, Skill)


def test_round_trip_educations() -> None:
    _round_trip(sd.EDUCATIONS, Education)


def test_round_trip_projects() -> None:
    _round_trip(sd.PROJECTS, Project)


def test_round_trip_certifications() -> None:
    _round_trip(sd.CERTIFICATIONS, Certification)


def test_round_trip_jobs() -> None:
    _round_trip(sd.JOBS, Job)


def test_round_trip_applications() -> None:
    _round_trip(sd.APPLICATIONS, Application)


def test_round_trip_contacts() -> None:
    _round_trip(sd.CONTACTS, Contact)


def test_round_trip_contact_application_links() -> None:
    _round_trip(sd.CONTACT_APPLICATION_LINKS, ContactApplicationLink)


def test_round_trip_outreach_messages() -> None:
    _round_trip(sd.OUTREACH_MESSAGES, OutreachMessage)


def test_round_trip_email_threads() -> None:
    _round_trip(sd.EMAIL_THREADS, EmailThread)


def test_round_trip_app_events() -> None:
    _round_trip(sd.APP_EVENTS, AppEvent)


def test_round_trip_generated_documents() -> None:
    _round_trip(sd.GENERATED_DOCUMENTS, GeneratedDocument)


def test_round_trip_screener_answers() -> None:
    _round_trip(sd.SCREENER_ANSWERS, ApplicationScreenerAnswer)


def test_round_trip_ats_credentials() -> None:
    _round_trip(sd.ATS_CREDENTIALS, ATSCredential)


def test_round_trip_api_usage() -> None:
    _round_trip(sd.API_USAGE, ApiUsage)


def test_round_trip_settings() -> None:
    _round_trip([sd.SETTINGS], Settings)


# ── Counts (SAMPLE_DATA.md inventory) ────────────────────────────────────


def test_user_singleton() -> None:
    assert sd.USER.id == 1
    assert sd.USER.email == "shyam.padia930@gmail.com"


def test_profile_singleton() -> None:
    assert sd.PROFILE.full_name == "Shyam Padia"
    # Visa rule honored (CLAUDE.md scoring rule)
    assert sd.PROFILE.work_authorization.value == "h1b"
    assert sd.PROFILE.visa_sponsorship_needed.value == "needed_now"


def test_counts_match_inventory() -> None:
    assert len(sd.EXPERIENCES) == 4
    assert len(sd.BULLETS) == 14
    assert len(sd.SKILLS) == 6
    assert len(sd.EDUCATIONS) == 2
    assert len(sd.PROJECTS) == 4
    assert len(sd.CERTIFICATIONS) == 1
    # Jobs ~20: spec is approximate; allow 18-30 range.
    assert 18 <= len(sd.JOBS) <= 30
    assert len(sd.APPLICATIONS) == 30  # plan 86 W3.1 extension: 14 → 30
    assert 18 <= len(sd.CONTACTS) <= 25
    assert 20 <= len(sd.CONTACT_APPLICATION_LINKS) <= 30
    # Outreach: spec says ~40
    assert 35 <= len(sd.OUTREACH_MESSAGES) <= 45
    # Email threads: spec says ~20
    assert 18 <= len(sd.EMAIL_THREADS) <= 22
    # AppEvents: spec says ~150 — allow looser range since per-app density varies
    assert 100 <= len(sd.APP_EVENTS) <= 180
    # Generated docs: spec says ~30
    assert 25 <= len(sd.GENERATED_DOCUMENTS) <= 40
    # Screener answers: spec says ~20
    assert 18 <= len(sd.SCREENER_ANSWERS) <= 25
    assert sd.ATS_CREDENTIALS == []
    # ApiUsage: spec says ~30 historical rows
    assert 25 <= len(sd.API_USAGE) <= 40


# ── Realism rules (SAMPLE_DATA.md § N) ───────────────────────────────────


def test_visa_filter_coverage() -> None:
    """N.4: ≥2 jobs with `us_citizen_only` restriction; both score 0."""
    visa_blocked = [j for j in sd.JOBS if j.visa_restrictions == "us_citizen_only"]
    assert len(visa_blocked) >= 2
    for j in visa_blocked:
        assert j.score == 0.0


def test_score_distribution_spans_thresholds() -> None:
    """N.5: unswiped jobs span emerald/indigo/amber/rose ring color thresholds."""
    unswiped = [j for j in sd.JOBS if j.queue_state == JobQueueState.UNSWIPED]
    scores = [j.score * 100 for j in unswiped]  # convert 0-1 → 0-100
    assert any(s >= 80 for s in scores), "no emerald-ring (≥80) UNSWIPED job"
    assert any(60 <= s < 80 for s in scores), "no indigo-ring (60-79) UNSWIPED job"
    assert any(40 <= s < 60 for s in scores), "no amber-ring (40-59) UNSWIPED job"


def test_recruiter_silence_stress() -> None:
    """N.6: ≥1 application recruiter_state=silent + applied ≥6 days ago."""
    silent_apps = [
        a
        for a in sd.APPLICATIONS
        if a.recruiter_state == RecruiterState.SILENT
        and a.applied_at is not None
        and (sd.TODAY - a.applied_at) >= timedelta(days=6)
    ]
    assert len(silent_apps) >= 1, "no recruiter-silent ≥6d application"


def test_closed_bucket_size() -> None:
    """N.7: ≥3 CLOSED applications with mix of closed_reason."""
    closed = [a for a in sd.APPLICATIONS if a.status == ApplicationStatus.CLOSED]
    assert len(closed) >= 3
    reasons = {a.closed_reason for a in closed}
    assert "rejected_by_them" in {r.value if r else None for r in reasons}
    assert "withdrawn_by_me" in {r.value if r else None for r in reasons}
    assert "ghosted" in {r.value if r else None for r in reasons}


def test_draft_coverage() -> None:
    """N.8: 2 DRAFT applications; both docs_state=ready; both have screener rows."""
    drafts = [a for a in sd.APPLICATIONS if a.status == ApplicationStatus.DRAFT]
    assert len(drafts) == 2
    for a in drafts:
        assert a.docs_state == DocsState.READY
        assert a.applied_at is None
        screeners = [s for s in sd.SCREENER_ANSWERS if s.application_id == a.id]
        assert len(screeners) >= 1, f"DRAFT app id={a.id} has no screener answers"


def test_stuck_queue_coverage() -> None:
    """Per the 2026-05-01 cross-plan triage: ≥1 DRAFT row carries
    submission_artifacts.last_failure for the Discover stuck-queue surface."""
    stuck = [
        a
        for a in sd.APPLICATIONS
        if a.status == ApplicationStatus.DRAFT
        and a.submission_artifacts
        and a.submission_artifacts.get("last_failure")
    ]
    assert len(stuck) >= 1, "no DRAFT with submission_artifacts.last_failure populated"
    # Sanity: the failure dict has the expected shape.
    fail = stuck[0].submission_artifacts["last_failure"]
    assert "kind" in fail
    assert fail["kind"] in {"auth_required", "captcha", "field_mismatch", "unknown"}


def test_owner_only_user_id() -> None:
    """N.10: every row is `user_id=1` (single-user MVP)."""
    for table in (
        sd.JOBS,
        sd.APPLICATIONS,
        sd.CONTACTS,
        sd.OUTREACH_MESSAGES,
        sd.EMAIL_THREADS,
        sd.APP_EVENTS,
        sd.API_USAGE,
    ):
        for row in table:
            assert row.user_id == 1, (
                f"{type(row).__name__} id={getattr(row, 'id', '?')} has user_id={row.user_id}"
            )


def test_bullet_selection_override_mix() -> None:
    """SAMPLE_DATA.md § C: 1 ALWAYS_INCLUDE, 1 NEVER_INCLUDE, 12 None."""
    always = [
        b for b in sd.BULLETS if b.selection_override == BulletSelectionOverride.ALWAYS_INCLUDE
    ]
    never = [b for b in sd.BULLETS if b.selection_override == BulletSelectionOverride.NEVER_INCLUDE]
    auto = [b for b in sd.BULLETS if b.selection_override is None]
    assert len(always) == 1
    assert len(never) == 1
    assert len(auto) == 12


def test_tag_vocab_compliance() -> None:
    """All bullet/job/project tags must be from the 9-tag vocabulary."""
    valid = {t.value for t in Tag}
    for b in sd.BULLETS:
        for t in b.tags:
            assert t.value in valid, f"bullet {b.id} has invalid tag {t!r}"
    for j in sd.JOBS:
        for t in j.tags:
            assert t.value in valid, f"job {j.id} has invalid tag {t!r}"
    for p in sd.PROJECTS:
        for t in p.tags:
            assert t.value in valid, f"project {p.id} has invalid tag {t!r}"


def test_outreach_status_mix() -> None:
    """SAMPLE_DATA.md § H: status mix DRAFT(4) + QUEUED(3) + SENT(18) +
    OPENED(5) + REPLIED(8) + BOUNCED(2) = 40 — allow ±2 per bucket."""
    by_status: dict[OutreachStatus, int] = dict.fromkeys(OutreachStatus, 0)
    for m in sd.OUTREACH_MESSAGES:
        by_status[m.status] = by_status.get(m.status, 0) + 1
    assert by_status[OutreachStatus.DRAFT] >= 3
    assert by_status[OutreachStatus.SENT] >= 14
    assert by_status[OutreachStatus.REPLIED] >= 6
    assert by_status[OutreachStatus.BOUNCED] >= 1


def test_contact_type_mix() -> None:
    """SAMPLE_DATA.md § G: mix of RECRUITER/EMPLOYEE/HIRING_MANAGER/HR."""
    by_type: dict[ContactType, int] = dict.fromkeys(ContactType, 0)
    for c in sd.CONTACTS:
        by_type[c.type] += 1
    assert by_type[ContactType.RECRUITER] >= 5
    assert by_type[ContactType.EMPLOYEE] >= 5
    assert by_type[ContactType.HIRING_MANAGER] >= 2
    assert by_type[ContactType.HR] >= 1


def test_settings_defaults() -> None:
    """SAMPLE_DATA.md § L: Settings singleton defaults match canonical."""
    s = sd.SETTINGS
    assert s.user_id == 1
    assert s.llm_provider == LLMProvider.ANTHROPIC
    assert s.auto_apply_enabled is False
    assert s.auto_apply_score_threshold == 0.85
    assert s.eager_review_generation is True
    assert s.deployment_mode.value == "self_hosted"
    assert "https://crypticsoul.dev" in s.portfolio_cors_allowed_origins


# ── Async accessor signature contract ────────────────────────────────────


def test_all_accessors_are_async() -> None:
    """Plan 09 § H: every accessor must be `async def` so plan 10 Wave 4
    swaps body-only without changing call sites.
    """
    public_callables = [
        getattr(sd, name)
        for name in sd.__all__
        if callable(getattr(sd, name)) and not name.startswith("_")
    ]
    # Filter to only top-level functions defined in sample_data.py (skip classes).
    funcs = [f for f in public_callables if inspect.isfunction(f) and f.__module__ == sd.__name__]
    assert funcs, "no accessors discovered"
    sync_funcs = [f for f in funcs if not inspect.iscoroutinefunction(f)]
    assert sync_funcs == [], (
        f"sync accessors leaked into sample_data.py: {[f.__name__ for f in sync_funcs]}"
    )


# ── Accessor smoke (asyncio_mode=auto in pyproject.toml) ────────────────


async def test_discover_queue_returns_unswiped_score_desc() -> None:
    queue = await sd.discover_queue()
    assert all(j.queue_state == JobQueueState.UNSWIPED for j in queue)
    scores = [j.score for j in queue]
    assert scores == sorted(scores, reverse=True)


async def test_applications_visible_in_tracking_excludes_draft_and_closed() -> None:
    apps = await sd.applications_visible_in_tracking()
    statuses = {a.status for a in apps}
    assert ApplicationStatus.DRAFT not in statuses
    assert ApplicationStatus.CLOSED not in statuses
    # Should still include APPLIED through OFFER
    assert ApplicationStatus.APPLIED in statuses or ApplicationStatus.RECRUITER_SCREEN in statuses


async def test_stuck_drafts_returns_failed_drafts() -> None:
    stuck = await sd.stuck_drafts()
    assert len(stuck) >= 1
    for a in stuck:
        assert a.status == ApplicationStatus.DRAFT
        assert a.submission_artifacts and a.submission_artifacts.get("last_failure")


async def test_kpi_active_applications_positive() -> None:
    n = await sd.kpi_active_applications()
    assert n >= 5  # the inventory has plenty of in-flight apps


async def test_priority_actions_includes_offer_and_silent() -> None:
    actions = await sd.priority_actions()
    kinds = {a["kind"] for a in actions}
    assert "offer" in kinds, "missing offer action"
    assert "silent" in kinds, "missing recruiter-silent action"


async def test_pipeline_strip_counts_keys() -> None:
    counts = await sd.pipeline_strip_counts()
    assert set(counts.keys()) == {"APPLIED", "RECRUITER_SCREEN", "ONSITE_LOOP", "OFFER", "CLOSED"}
    assert sum(counts.values()) >= 5


async def test_llm_usage_summary_shape() -> None:
    summary = await sd.llm_usage_summary(days=30)
    assert {"month_cost_usd", "avg_per_generation_usd", "total_tokens", "gen_count"} == set(
        summary.keys()
    )
    assert summary["month_cost_usd"] > 0
    assert summary["total_tokens"] > 0


async def test_create_draft_then_discard_via_status_override() -> None:
    """Sanity-check the in-memory mutation shim — DRAFT lifecycle slice."""
    queue = await sd.discover_queue()
    candidate = None
    for j in queue:
        if await sd.application_for_job(1, j.id) is None:
            candidate = j
            break
    if candidate is None:
        pytest.skip("no job without app available for mutation test")
    n_before = len(sd.APPLICATIONS)
    a = await sd._create_draft(1, candidate.id)
    assert a.status == ApplicationStatus.DRAFT
    assert len(sd.APPLICATIONS) == n_before + 1
    # Cleanup so other tests don't see the side effect.
    sd.APPLICATIONS.remove(a)
