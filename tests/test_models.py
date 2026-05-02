"""SQLModel entity tests — Wave 4 of plan 10.

Verifies:
- Every SQLModel entity instantiates from in-memory fixtures (no live DB).
- Field shape mirrors `db/sample_data_models.py` (Pydantic shadows).
- AppEvent payload discriminated union round-trips per DATA_MODEL.md § M.

Live-DB behavior (CHECK constraints, indexes, ENUM types) requires Postgres
and is exercised by `tests/test_seed.py` when DATABASE_URL points at a
running Postgres instance.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from db import sample_data as sd
from models import (
    ApiUsage,
    AppEvent,
    Application,
    ApplicationScreenerAnswer,
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
from models.app_event_payloads import (
    DocsGeneratedPayload,
    EmailReceivedPayload,
    StatusChangePayload,
    dump_payload,
    parse_payload,
)
from models.enums import (
    AppEventKind,
    EmailClassification,
    GeneratedDocumentKind,
    StatusChangeTrigger,
)

# ── Instantiation: every entity round-trips from sample_data shadows ─────


def _convert(shadow_obj, sql_cls):
    """Convert a Pydantic shadow instance to a SQLModel instance via dict dump."""
    raw = shadow_obj.model_dump(mode="python")
    return sql_cls.model_validate(raw)


def test_user_instantiates() -> None:
    user = _convert(sd.USER, User)
    assert user.email == "shyam.padia930@gmail.com"
    assert user.is_active is True


def test_profile_instantiates() -> None:
    profile = _convert(sd.PROFILE, Profile)
    assert profile.full_name == "Shyam Padia"
    assert profile.work_authorization is not None


def test_experiences_instantiate() -> None:
    items = [_convert(e, Experience) for e in sd.EXPERIENCES]
    assert len(items) >= 4
    assert all(e.start_date is not None for e in items)


def test_bullets_instantiate() -> None:
    items = [_convert(b, Bullet) for b in sd.BULLETS]
    assert len(items) >= 14
    assert all(len(b.text) > 0 for b in items)


def test_skills_instantiate() -> None:
    items = [_convert(s, Skill) for s in sd.SKILLS]
    assert len(items) >= 5
    assert all(len(s.items) > 0 for s in items)


def test_educations_instantiate() -> None:
    items = [_convert(e, Education) for e in sd.EDUCATIONS]
    assert len(items) >= 2


def test_projects_instantiate() -> None:
    items = [_convert(p, Project) for p in sd.PROJECTS]
    assert len(items) >= 3


def test_certifications_instantiate() -> None:
    items = [_convert(c, Certification) for c in sd.CERTIFICATIONS]
    assert len(items) >= 1


def test_jobs_instantiate() -> None:
    items = [_convert(j, Job) for j in sd.JOBS]
    assert len(items) >= 18
    for j in items:
        assert 0.0 <= j.score <= 1.0


def test_applications_instantiate() -> None:
    items = [_convert(a, Application) for a in sd.APPLICATIONS]
    assert len(items) >= 14
    drafts = [a for a in items if a.status.value == "DRAFT"]
    assert len(drafts) >= 2
    for d in drafts:
        assert d.applied_at is None  # DRAFT pre-submission


def test_contacts_instantiate() -> None:
    items = [_convert(c, Contact) for c in sd.CONTACTS]
    assert len(items) >= 18


def test_contact_application_links_instantiate() -> None:
    items = [
        _convert(link, ContactApplicationLink) for link in sd.CONTACT_APPLICATION_LINKS
    ]
    assert len(items) >= 20


def test_outreach_messages_instantiate() -> None:
    items = [_convert(m, OutreachMessage) for m in sd.OUTREACH_MESSAGES]
    assert len(items) >= 35


def test_email_threads_instantiate() -> None:
    items = [_convert(t, EmailThread) for t in sd.EMAIL_THREADS]
    assert len(items) >= 18
    assert all(t.latest_message_at is not None for t in items)


def test_app_events_instantiate() -> None:
    items = [_convert(e, AppEvent) for e in sd.APP_EVENTS]
    assert len(items) >= 100


def test_generated_documents_instantiate() -> None:
    items = [_convert(d, GeneratedDocument) for d in sd.GENERATED_DOCUMENTS]
    assert len(items) >= 25
    for d in items:
        assert d.byte_size >= 0  # placeholder fixtures may carry 0 bytes


def test_screener_answers_instantiate() -> None:
    items = [_convert(s, ApplicationScreenerAnswer) for s in sd.SCREENER_ANSWERS]
    assert len(items) >= 18


def test_ats_credentials_empty_in_phase1() -> None:
    assert sd.ATS_CREDENTIALS == []


def test_api_usage_seeds() -> None:
    items = [_convert(u, ApiUsage) for u in sd.API_USAGE]
    assert len(items) >= 10
    for u in items:
        assert u.cost_usd >= 0


def test_settings_singleton() -> None:
    settings = _convert(sd.SETTINGS, Settings)
    assert settings.user_id == 1
    assert settings.eager_review_generation is True
    assert "https://crypticsoul.dev" in settings.portfolio_cors_allowed_origins


# ── AppEvent payload schemas (DATA_MODEL.md § M) ────────────────────────


def test_status_change_payload_round_trip() -> None:
    payload = StatusChangePayload(
        from_status="DRAFT",
        to_status="APPLIED",
        triggered_by=StatusChangeTrigger.DRAFT_SUBMITTED,
    )
    raw = dump_payload(payload)
    reparsed = parse_payload(AppEventKind.STATUS_CHANGE, raw)
    assert reparsed.to_status == "APPLIED"
    assert reparsed.triggered_by is StatusChangeTrigger.DRAFT_SUBMITTED


def test_docs_generated_payload_round_trip() -> None:
    payload = DocsGeneratedPayload(
        generated_document_id=712,
        document_kind=GeneratedDocumentKind.RESUME,
        model="claude-3.5-sonnet-20250219",
        cost_usd=0.04,
        token_count=1822,
        page_count=1,
    )
    raw = dump_payload(payload)
    reparsed = parse_payload(AppEventKind.DOCS_GENERATED, raw)
    assert reparsed.cost_usd == 0.04
    assert reparsed.page_count == 1


def test_email_received_payload_round_trip() -> None:
    payload = EmailReceivedPayload(
        thread_id=412,
        message_id_external="abc123",
        sender="recruiter@anthropic.com",
        subject_preview="Anthropic — next step",
        classification=EmailClassification.INTERVIEW_REQUEST,
        urgent=True,
    )
    raw = dump_payload(payload)
    reparsed = parse_payload(AppEventKind.EMAIL_RECEIVED, raw)
    assert reparsed.classification is EmailClassification.INTERVIEW_REQUEST
    assert reparsed.urgent is True


# ── Application invariants (validated by Pydantic; CHECK constraints
# verified at the Postgres layer in tests/test_seed.py) ────────────────


def test_application_closed_requires_reason_in_app_logic() -> None:
    """Discarded DRAFT case: status=CLOSED, closed_reason=withdrawn_by_me,
    deleted_at set, applied_at=None — must instantiate cleanly per the
    corrected 2026-05-01 CHECK constraint."""
    from models.enums import (
        ApplicationBoard,
        ApplicationStatus,
        ClosedReason,
        DocsState,
        RecruiterState,
        ReferralState,
    )

    now = datetime.now(UTC)
    app = Application(
        id=99,
        user_id=1,
        job_id=None,
        company="Test Co",
        role="Test Role",
        applied_at=None,
        board=ApplicationBoard.MANUAL,
        status=ApplicationStatus.CLOSED,
        closed_reason=ClosedReason.WITHDRAWN_BY_ME,
        docs_state=DocsState.NONE,
        referral_state=ReferralState.NONE,
        recruiter_state=RecruiterState.NONE,
        deleted_at=now,
        created_at=now - timedelta(days=1),
        updated_at=now,
    )
    assert app.status is ApplicationStatus.CLOSED
    assert app.closed_reason is ClosedReason.WITHDRAWN_BY_ME
    assert app.applied_at is None
    assert app.deleted_at is not None


def test_settings_defaults() -> None:
    s = Settings(user_id=42)
    # Default Settings instantiates cleanly with no required overrides
    assert s.llm_provider.value == "anthropic"
    assert s.eager_review_generation is True
    assert s.daily_llm_cost_cap_usd is None
    assert s.portfolio_cors_allowed_origins == ["https://crypticsoul.dev"]
    assert s.debug is False
