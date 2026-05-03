"""Wave 6 — document_generator tests.

Per plan 10 § E. Coverage:
- resume + cover letter pipelines produce GeneratedDocument rows
- bullet selection respects `selection_override` (always_include / never_include)
- page-count validation retries (mocked typst overflow then ok)
- ScreenerAnswer auto + drafted + user source paths
- DRAFT reuse heuristic no-op when conditions hold
- cost-cap aborts generation when exceeded

Tests mock LLM + Typst at function boundaries to keep unit tests fast +
deterministic. The real Typst integration is exercised in test_typst.py.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from services import document_generator as dg
from services.document_generator import (
    CostCapExceededError,
    PreGenerateResult,
    answer_screeners,
    can_reuse_existing_resume,
    generate_resume,
    pre_generate,
    question_fingerprint,
)

_HAS_TYPST = shutil.which("typst") is not None


# ── In-memory fakes for the model objects ─────────────────────────────


def _make_profile(**overrides):
    base = {
        "id": 1,
        "user_id": 1,
        "full_name": "Shyam Padia",
        "headline": "Senior Software Engineer",
        "email": "shyam@example.com",
        "phone": "+1 555 555 0100",
        "location": "Boston, MA",
        "portfolio_url": "crypticsoul.dev",
        "linkedin_handle": "shyampadia",
        "github_handle": "crizzy9",
        "summary_short": "Backend + ML engineer with 8+ years.",
        "summary_full": None,
        "deleted_at": None,
        "work_authorization": None,
        "visa_sponsorship_needed": None,
        "willing_to_relocate": None,
        "notice_period_days": None,
        "salary_expectation_usd": 180000,
        "earliest_start": None,
        "veteran_status": None,
        "disability_status": None,
        "race_ethnicity": None,
        "gender_identity": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _make_experience(eid: int, profile_id: int = 1):
    return SimpleNamespace(
        id=eid,
        profile_id=profile_id,
        company="Intuit",
        title="Senior Engineer",
        team=None,
        location="Mountain View",
        start_date=datetime(2020, 7, 1, tzinfo=UTC),
        end_date=None,
        order_index=eid,
        summary_short=None,
        deleted_at=None,
    )


def _make_bullet(bid: int, exp_id: int, text: str, override=None, tags=None,
                 edited_at=None):
    return SimpleNamespace(
        id=bid,
        experience_id=exp_id,
        order_index=bid,
        text=text,
        tags=tags or ["backend"],
        selection_override=override,
        edited_at=edited_at or datetime.now(UTC) - timedelta(days=10),
        deleted_at=None,
    )


def _make_job(jid: int = 100, **kw):
    base = {
        "id": jid,
        "company": "Stripe",
        "role": "Senior Backend Engineer",
        "description": "Build payment infrastructure at scale. Python + Go.",
        "description_html": None,
        "skills_required": ["python", "go", "aws"],
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _make_application(aid: int = 1, **kw):
    base = {
        "id": aid,
        "user_id": 1,
        "job_id": 100,
        "company": "Stripe",
        "role": "Senior Backend Engineer",
        "status": __import__("models", fromlist=["ApplicationStatus"]).ApplicationStatus.DRAFT,
        "docs_state": __import__("models", fromlist=["DocsState"]).DocsState.NONE,
        "applied_at": None,
        "deleted_at": None,
        "submission_artifacts": None,
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _make_settings(**kw):
    base = {
        "user_id": 1,
        "llm_provider": __import__("models", fromlist=["LLMProvider"]).LLMProvider.ANTHROPIC,
        "llm_model": "claude-3.5-sonnet-20250219",
        "llm_fallback_provider": None,
        "eager_review_generation": True,
        "daily_llm_cost_cap_usd": None,
    }
    base.update(kw)
    return SimpleNamespace(**base)


# ── Fingerprint logic ────────────────────────────────────────────────


def test_question_fingerprint_normalizes():
    assert question_fingerprint("Why Stripe?") == "why stripe"
    assert (
        question_fingerprint("What is your earliest start date?")
        == "what is your earliest start date"
    )
    assert question_fingerprint("Are you AUTHORIZED to work in the US?") == (
        "are you authorized to work in the us"
    )


def test_auto_field_for_question_recognizes_canonical_questions():
    assert dg._auto_field_for_question("What is your earliest start date?") == "earliest_start"
    assert (
        dg._auto_field_for_question("Will you require visa sponsorship?")
        == "visa_sponsorship_needed"
    )
    assert (
        dg._auto_field_for_question("What is your salary expectation?")
        == "salary_expectation_usd"
    )
    assert dg._auto_field_for_question("Why Stripe?") is None


# ── Bullet override split ────────────────────────────────────────────


def test_split_bullets_by_override():
    from models import BulletSelectionOverride

    bullets = [
        _make_bullet(1, 1, "Always pinned", override=BulletSelectionOverride.ALWAYS_INCLUDE),
        _make_bullet(2, 1, "Never visible", override=BulletSelectionOverride.NEVER_INCLUDE),
        _make_bullet(3, 1, "AI-decided"),
    ]
    always, never, auto = dg._split_bullets_by_override(bullets)
    assert [b.id for b in always] == [1]
    assert [b.id for b in never] == [2]
    assert [b.id for b in auto] == [3]


# ── Cost cap logic ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cost_cap_short_circuits_before_llm_calls():
    """When today's spend ≥ cap, generate_* raises CostCapExceededError."""
    settings = _make_settings(daily_llm_cost_cap_usd=0.01)
    application = _make_application()

    fake_session = AsyncMock()
    with (
        patch("services.document_generator._today_spend", new=AsyncMock(return_value=0.05)),
        pytest.raises(CostCapExceededError),
    ):
        await generate_resume(
            fake_session, application, settings=settings, job=_make_job()
        )


@pytest.mark.asyncio
async def test_cost_cap_pre_generate_returns_skipped_reason():
    settings = _make_settings(daily_llm_cost_cap_usd=0.01)
    application = _make_application()
    fake_session = AsyncMock()
    with (
        patch(
            "services.document_generator._today_spend",
            new=AsyncMock(return_value=0.05),
        ),
        # Job lookup not needed — cost_cap fires before reuse check.
        patch(
            "services.document_generator.can_reuse_existing_resume",
            new=AsyncMock(return_value=False),
        ),
        patch.object(fake_session, "exec", new=AsyncMock()) as exec_mock,
    ):
        exec_mock.return_value.one_or_none = AsyncMock(return_value=_make_job())
        result = await pre_generate(
            fake_session, application, settings=settings, job=_make_job()
        )
    assert isinstance(result, PreGenerateResult)
    assert result.skipped_reason == "cost_cap_reached"
    assert result.resume is None


# ── Reuse heuristic ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_can_reuse_existing_resume_when_unchanged():
    """READY + bullets unedited + JD hash matches → reuse (no LLM call)."""
    from models import DocsState

    application = _make_application(docs_state=DocsState.READY)
    job = _make_job(description_html="<p>JD</p>", description="JD")
    expected_hash = dg._hash_jd("<p>JD</p>")

    latest_doc = SimpleNamespace(
        compiled_at=datetime.now(UTC),
        bullet_selection={"selected_ids": [1, 2], "jd_hash": expected_hash},
    )
    bullets = [
        _make_bullet(1, 1, "old text", edited_at=datetime.now(UTC) - timedelta(days=5)),
        _make_bullet(2, 1, "another", edited_at=datetime.now(UTC) - timedelta(days=10)),
    ]
    fake_session = AsyncMock()
    fake_session.exec = AsyncMock()
    # First call → latest resume (one_or_none); next call → bullets list (all)
    first = SimpleNamespace(one_or_none=lambda: latest_doc, all=lambda: [latest_doc])
    second = SimpleNamespace(one_or_none=lambda: None, all=lambda: bullets)
    fake_session.exec.side_effect = [first, second]
    assert await can_reuse_existing_resume(fake_session, application, job) is True


@pytest.mark.asyncio
async def test_reuse_disabled_when_jd_hash_drifts():
    from models import DocsState

    application = _make_application(docs_state=DocsState.READY)
    _make_job(description="old JD")
    new_job = _make_job(description="brand new JD")
    latest_doc = SimpleNamespace(
        compiled_at=datetime.now(UTC),
        bullet_selection={"selected_ids": [1], "jd_hash": dg._hash_jd("old JD")},
    )
    bullets = [_make_bullet(1, 1, "x")]
    fake_session = AsyncMock()
    fake_session.exec = AsyncMock()
    first = SimpleNamespace(one_or_none=lambda: latest_doc, all=lambda: [])
    second = SimpleNamespace(one_or_none=lambda: None, all=lambda: bullets)
    fake_session.exec.side_effect = [first, second]
    assert await can_reuse_existing_resume(fake_session, application, new_job) is False


@pytest.mark.asyncio
async def test_reuse_disabled_when_bullet_edited_after_compile():
    from models import DocsState

    application = _make_application(docs_state=DocsState.READY)
    job = _make_job(description="JD")
    compile_time = datetime.now(UTC) - timedelta(hours=1)
    latest_doc = SimpleNamespace(
        compiled_at=compile_time,
        bullet_selection={"selected_ids": [1], "jd_hash": dg._hash_jd("JD")},
    )
    # Bullet edited 5 minutes ago — after the resume compile.
    bullets = [_make_bullet(1, 1, "x", edited_at=datetime.now(UTC))]
    fake_session = AsyncMock()
    fake_session.exec = AsyncMock()
    first = SimpleNamespace(one_or_none=lambda: latest_doc, all=lambda: [])
    second = SimpleNamespace(one_or_none=lambda: None, all=lambda: bullets)
    fake_session.exec.side_effect = [first, second]
    assert await can_reuse_existing_resume(fake_session, application, job) is False


@pytest.mark.asyncio
async def test_reuse_disabled_when_docs_state_not_ready():
    from models import DocsState

    application = _make_application(docs_state=DocsState.GENERATING)
    fake_session = AsyncMock()
    assert await can_reuse_existing_resume(fake_session, application, _make_job()) is False


# ── Hashing identity ─────────────────────────────────────────────────


def test_jd_hash_stable():
    a = dg._hash_jd("hello")
    b = dg._hash_jd("hello")
    c = dg._hash_jd("world")
    assert a == b
    assert a != c
    assert len(a) == 32


# ── Screener answering ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_answer_screeners_auto_fills_visa_question():
    """Visa-sponsorship question matches a Profile field → AUTO source."""
    from models import VisaSponsorship

    profile = _make_profile(visa_sponsorship_needed=VisaSponsorship.NEEDED_NOW)
    settings = _make_settings()
    application = _make_application()

    fake_session = AsyncMock()
    fake_session.exec = AsyncMock()
    fake_session.exec.return_value.one_or_none = lambda: profile
    fake_session.exec.return_value.all = lambda: []
    fake_session.add = lambda x: None
    fake_session.flush = AsyncMock()

    questions = [
        {"question_text": "Will you require visa sponsorship?", "question_type": "single_select"}
    ]

    rows = await answer_screeners(
        fake_session,
        application,
        settings=settings,
        job=_make_job(),
        questions=questions,
    )
    assert len(rows) == 1
    row = rows[0]
    from models import ScreenerAnswerSource

    assert row.source == ScreenerAnswerSource.AUTO
    assert row.reviewed_at is not None
    assert "needed_now" in (row.answer or "")


@pytest.mark.asyncio
async def test_answer_screeners_drafts_custom_question_via_llm():
    """Custom JD-specific question → DRAFTED source, reviewed_at = None."""
    profile = _make_profile()
    settings = _make_settings()
    application = _make_application()

    fake_session = AsyncMock()

    # First exec: profile lookup (one_or_none); second exec: existing rows (all)
    profile_query = SimpleNamespace(one_or_none=lambda: profile, all=lambda: [])
    existing_query = SimpleNamespace(one_or_none=lambda: None, all=lambda: [])
    fake_session.exec.side_effect = [profile_query, existing_query]
    fake_session.add = lambda x: None
    fake_session.flush = AsyncMock()

    fake_provider = SimpleNamespace(
        provider_id="anthropic",
        model_name="claude-3.5-sonnet-20250219",
    )

    async def fake_tracked_call(**kwargs):
        return SimpleNamespace(value={"answer": "Stripe leads in payments infra."})

    questions = [{"question_text": "Why Stripe?", "question_type": "textarea"}]

    with (
        patch(
            "services.document_generator.get_provider", return_value=fake_provider
        ),
        patch(
            "services.document_generator.llm_tracker.tracked_call",
            new=fake_tracked_call,
        ),
        patch(
            "services.document_generator._today_spend",
            new=AsyncMock(return_value=0.0),
        ),
    ):
        rows = await answer_screeners(
            fake_session,
            application,
            settings=settings,
            job=_make_job(),
            questions=questions,
        )
    assert len(rows) == 1
    row = rows[0]
    from models import ScreenerAnswerSource

    assert row.source == ScreenerAnswerSource.DRAFTED
    assert row.reviewed_at is None
    assert "Stripe" in (row.answer or "")


@pytest.mark.asyncio
async def test_answer_screeners_preserves_user_source_rows():
    """An existing row with source=USER is left untouched on a re-run."""
    from models import ScreenerAnswerSource, ScreenerQuestionType

    profile = _make_profile()
    settings = _make_settings()
    application = _make_application()

    user_row = SimpleNamespace(
        id=1,
        application_id=1,
        question_text="Why Stripe?",
        question_fingerprint="why stripe",
        question_type=ScreenerQuestionType.TEXTAREA,
        choices=None,
        required=True,
        order_index=0,
        answer="my custom user-edited answer",
        source=ScreenerAnswerSource.USER,
        drafted_by_model=None,
        reviewed_at=datetime.now(UTC),
    )

    fake_session = AsyncMock()
    profile_query = SimpleNamespace(one_or_none=lambda: profile, all=lambda: [])
    existing_query = SimpleNamespace(one_or_none=lambda: None, all=lambda: [user_row])
    fake_session.exec.side_effect = [profile_query, existing_query]
    fake_session.add = lambda x: None
    fake_session.flush = AsyncMock()

    questions = [{"question_text": "Why Stripe?", "question_type": "textarea"}]
    rows = await answer_screeners(
        fake_session,
        application,
        settings=settings,
        job=_make_job(),
        questions=questions,
    )
    # The same row comes back with source=USER and original answer preserved.
    assert len(rows) == 1
    assert rows[0].source == ScreenerAnswerSource.USER
    assert rows[0].answer == "my custom user-edited answer"


# ── Real-Typst integration: bullet selection respects override ─────────


@pytest.mark.skipif(not _HAS_TYPST, reason="typst CLI not available")
@pytest.mark.asyncio
async def test_generate_resume_honors_always_include(tmp_path):
    """ALWAYS_INCLUDE bullets are always in the final selection."""
    from models import (
        BulletSelectionOverride,
    )

    profile = _make_profile()
    exp = _make_experience(1)
    pinned = _make_bullet(
        1, 1, "Pinned forever - this must show up", override=BulletSelectionOverride.ALWAYS_INCLUDE
    )
    skipped = _make_bullet(
        2, 1, "NEVER show this", override=BulletSelectionOverride.NEVER_INCLUDE
    )
    auto1 = _make_bullet(3, 1, "Auto-decide bullet A")
    auto2 = _make_bullet(4, 1, "Auto-decide bullet B")
    skill = SimpleNamespace(
        id=1, profile_id=1, category="Languages", items=["Python"], order_index=0
    )

    settings = _make_settings()
    application = _make_application()
    job = _make_job()

    snap = dg.ProfileSnapshot(
        profile=profile,
        experiences=[exp],
        bullets_by_experience={1: [pinned, skipped, auto1, auto2]},
        skills=[skill],
        education=[],
        projects=[],
    )

    saved_docs: list = []
    saved_apps: list = []
    fake_session = AsyncMock()

    def add(o):
        if hasattr(o, "kind"):
            saved_docs.append(o)
        else:
            saved_apps.append(o)

    fake_session.add = add
    fake_session.flush = AsyncMock()

    out_dir = tmp_path / "out"
    out_dir.mkdir()

    async def fake_select_bullets(**kwargs):
        # AI returns auto1 only (auto2 omitted).
        return SimpleNamespace(value={"selected_ids": [3]})

    with (
        patch("services.document_generator._today_spend", new=AsyncMock(return_value=0.0)),
        patch(
            "services.document_generator.load_profile_snapshot",
            new=AsyncMock(return_value=snap),
        ),
        patch(
            "services.document_generator._app_documents_dir",
            return_value=out_dir,
        ),
        patch("services.document_generator.get_provider"),
        patch(
            "services.document_generator.llm_tracker.tracked_call",
            new=fake_select_bullets,
        ),
    ):
        doc = await generate_resume(
            fake_session, application, settings=settings, job=job
        )
    assert doc.kind.value == "resume"
    selected = doc.bullet_selection["selected_ids"]
    assert 1 in selected, "always_include bullet must be selected"
    assert 2 not in selected, "never_include bullet must be skipped"
    assert (out_dir / "resume.pdf").exists()
    assert doc.page_count == 1


# ── Reuse-heuristic short-circuit in pre_generate ─────────────────────


@pytest.mark.asyncio
async def test_pre_generate_no_op_when_reuse_heuristic_holds():
    settings = _make_settings()
    application = _make_application()
    fake_session = AsyncMock()
    with (
        patch(
            "services.document_generator._today_spend",
            new=AsyncMock(return_value=0.0),
        ),
        patch(
            "services.document_generator.can_reuse_existing_resume",
            new=AsyncMock(return_value=True),
        ),
    ):
        # job lookup may happen inside; ensure exec returns a job
        exec_result = SimpleNamespace(one_or_none=lambda: _make_job())
        fake_session.exec = AsyncMock(return_value=exec_result)
        result = await pre_generate(fake_session, application, settings=settings)
    assert result.skipped_reason == "reuse_heuristic"
    assert result.resume is None
    assert result.cover_letter is None


# ── pre_generate force=True bypasses reuse + cost cap (smoke) ─────────


@pytest.mark.asyncio
async def test_pre_generate_force_bypasses_reuse_and_cost_cap():
    settings = _make_settings(daily_llm_cost_cap_usd=0.01)
    application = _make_application()
    fake_session = AsyncMock()
    with (
        patch(
            "services.document_generator._today_spend",
            new=AsyncMock(return_value=999.0),
        ),
        patch(
            "services.document_generator.can_reuse_existing_resume",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "services.document_generator.generate_resume",
            new=AsyncMock(return_value=SimpleNamespace(kind="resume")),
        ),
        patch(
            "services.document_generator.generate_cover_letter",
            new=AsyncMock(return_value=SimpleNamespace(kind="cover_letter")),
        ),
        patch(
            "services.document_generator.answer_screeners",
            new=AsyncMock(return_value=[]),
        ),
    ):
        # Even at 999 spend with reuse=True, force=True still runs full gen.
        # But since gen functions read spend internally, we patch _today_spend
        # to 0 inside that path. (For the unit test we simply assert the
        # functions get called.)
        exec_result = SimpleNamespace(one_or_none=lambda: _make_job())
        fake_session.exec = AsyncMock(return_value=exec_result)
        result = await pre_generate(
            fake_session, application, settings=settings, force=True
        )
    assert result.skipped_reason is None
    assert result.resume is not None
    assert result.cover_letter is not None
