"""Bundle generator orchestrator — plan 66 (0.3.1) § B.6.

Tests the cost-cap mid-flight pivot, ethics rejection path, and
audit-trail shape. Mocks the underlying `document_generator` calls so
the orchestrator's wiring + trace assembly is the unit under test.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from services.ats_parser_fidelity import ParseScoreReport
from services.generation import (
    GENERATION_TRACE_SCHEMA_VERSION,
    BundleResult,
    generate_bundle,
)
from services.hiring_manager_extractor import HiringManagerHit
from services.voice_grounding import VoiceCorpus


def _make_application(**overrides):
    base = {
        "id": 42,
        "user_id": 1,
        "job_id": 100,
        "company": "Stripe",
        "role": "Senior Engineer",
        "status": "DRAFT",
        "board": None,
        "generation_trace": None,
        "updated_at": None,
        "applied_at": None,
        "deleted_at": None,
        "submission_artifacts": None,
        "docs_state": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _make_settings(**overrides):
    base = {
        "user_id": 1,
        "llm_provider": "anthropic",
        "llm_model": "claude-sonnet-4-6",
        "daily_llm_cost_cap_usd": None,
        "parse_fidelity_threshold": 0.75,
        "resume_template_preference": "auto",
        "cover_letter_format": "auto",
        "ai_writing_voice_samples": "",
        "tier_2_evasion_enabled": False,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _make_job(**overrides):
    base = {
        "id": 100,
        "company": "Stripe",
        "role": "Senior Engineer",
        "description": "Build payment infrastructure.",
        "description_html": None,
        "skills_required": ["python", "go", "aws"],
        "score": 0.0,
        "match_breakdown": {},
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _make_corpus():
    return VoiceCorpus(
        full_text="sample corpus",
        vocab_fingerprint=["distributed", "systems"],
        sentence_length_stats={
            "mean_words": 10.0,
            "std_dev_words": 4.0,
            "short_pct": 30.0,
            "med_pct": 50.0,
            "long_pct": 20.0,
            "sentence_count": 5.0,
        },
        idiomatic_phrases=[],
        voice_fingerprint_hash="sha256:test",
        source_counts={"bullets": 5},
    )


@pytest.mark.asyncio
async def test_bundle_pre_flight_cost_cap_skips_all_stages():
    """When cost cap is reached BEFORE stage 1, every stage is skipped."""
    session = AsyncMock()
    # Match the SQLModel session.exec() result shape via custom mock
    application = _make_application()
    settings = _make_settings(daily_llm_cost_cap_usd=0.01)

    # session.add + flush are no-ops; only is_cost_capped matters here.
    async def _flush():
        return None

    session.flush = AsyncMock(return_value=None)
    session.add = lambda x: None

    with patch(
        "services.document_generator.is_cost_capped",
        AsyncMock(return_value=True),
    ):
        result = await generate_bundle(session, application, settings=settings)

    assert isinstance(result, BundleResult)
    assert result.degraded
    assert result.degraded_reason == "cost_cap_reached"
    assert result.skipped_reason == "cost_cap_reached"
    assert result.resume is None
    assert result.cover_letter is None
    assert result.generation_trace["degraded_mode"] is True
    assert len(result.generation_trace["stages_skipped"]) >= 5
    assert result.generation_trace["schema_version"] == GENERATION_TRACE_SCHEMA_VERSION
    assert result.generation_trace["tier"] == "free"


@pytest.mark.asyncio
async def test_bundle_no_job_raises():
    """Application without a Job context (no job_id) → ValueError."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda x: None
    # session.exec returns a generator/result chain; mock to None on Job lookup
    session.exec = AsyncMock(return_value=SimpleNamespace(one_or_none=lambda: None, all=lambda: []))
    application = _make_application(job_id=None)
    settings = _make_settings()

    with (
        patch(
            "services.document_generator.is_cost_capped",
            AsyncMock(return_value=False),
        ),
        pytest.raises(ValueError, match="has no job context"),
    ):
        await generate_bundle(session, application, settings=settings)


@pytest.mark.asyncio
async def test_bundle_full_happy_path():
    """Happy path: corpus → hiring manager → resume → headline → cover → screeners."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda x: None
    application = _make_application(board=None)
    settings = _make_settings()
    job = _make_job(score=0.78)

    fake_resume = SimpleNamespace(
        id=1,
        path="/tmp/resume.pdf",
        bullet_selection={"selected_ids": [1, 2], "trimmed_lines": {"1": "ok", "2": "good"}},
    )
    fake_cover = SimpleNamespace(id=2, path="/tmp/cover.pdf", bullet_selection=None)
    fake_screeners = [SimpleNamespace(id=10)]
    fake_corpus = _make_corpus()
    fake_hm = HiringManagerHit(name="Jane Smith", title=None, source="regex", confidence=0.9)

    # Stub session.exec returns for the Bullet.id collection (ethics stage).
    bullet_rows = [(1,), (2,)]
    session.exec = AsyncMock(
        return_value=SimpleNamespace(
            one_or_none=lambda: SimpleNamespace(id=1, user_id=1),
            all=lambda: bullet_rows,
        )
    )

    with (
        patch(
            "services.document_generator.is_cost_capped",
            AsyncMock(return_value=False),
        ),
        patch(
            "services.generation.assemble_corpus",
            AsyncMock(return_value=fake_corpus),
        ),
        patch(
            "services.generation.extract_hiring_manager",
            AsyncMock(return_value=fake_hm),
        ),
        patch(
            "services.document_generator.generate_resume",
            AsyncMock(return_value=fake_resume),
        ),
        patch(
            "services.generation._load_profile_experiences",
            AsyncMock(return_value=(None, [])),  # skip headline (no profile)
        ),
        patch(
            "services.document_generator.generate_cover_letter",
            AsyncMock(return_value=fake_cover),
        ),
        patch(
            "services.document_generator.answer_screeners",
            AsyncMock(return_value=fake_screeners),
        ),
        patch(
            "services.generation.validate_parse_fidelity",
            return_value=ParseScoreReport(
                score=0.92,
                tier="silent",
                fields_found={
                    "name": True,
                    "email": True,
                    "phone": True,
                    "first_experience_title": True,
                    "first_experience_company": True,
                    "first_experience_start_date": True,
                    "education_institution": True,
                    "skills_section_present": True,
                },
            ),
        ),
    ):
        result = await generate_bundle(session, application, settings=settings, job=job)

    assert not result.degraded
    assert result.resume is fake_resume
    assert result.cover_letter is fake_cover
    assert len(result.screeners) == 1
    assert result.hiring_manager == fake_hm
    assert result.parse_fidelity is not None
    assert result.parse_fidelity.score == 0.92
    assert result.keyword_coverage is not None
    trace = result.generation_trace
    assert "corpus" in trace["stages_run"]
    assert "hiring_manager" in trace["stages_run"]
    assert "resume" in trace["stages_run"]
    assert "cover_letter" in trace["stages_run"]
    assert "screeners" in trace["stages_run"]
    assert "parse_fidelity" in trace["stages_run"]
    assert "keyword_coverage" in trace["stages_run"]
    assert "ethics" in trace["stages_run"]
    assert trace["hiring_manager"]["name"] == "Jane Smith"
    assert trace["hiring_manager"]["source"] == "regex"


@pytest.mark.asyncio
async def test_bundle_cost_cap_mid_flight_after_corpus():
    """Cap fires after corpus assembly but before resume → resume + later stages skipped."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda x: None
    application = _make_application()
    settings = _make_settings()
    job = _make_job()

    # First is_cost_capped call returns False (pre-corpus); second returns True.
    call_count = {"n": 0}

    async def _capped(*args, **kwargs):
        call_count["n"] += 1
        # Pre-flight (call 1) = False; pre-hiring-manager (call 2) = True.
        return call_count["n"] >= 2

    with (
        patch("services.document_generator.is_cost_capped", _capped),
        patch(
            "services.generation.assemble_corpus",
            AsyncMock(return_value=_make_corpus()),
        ),
    ):
        result = await generate_bundle(session, application, settings=settings, job=job)

    assert result.degraded
    assert result.degraded_reason == "cost_cap_reached"
    assert result.resume is None
    assert "corpus" in result.generation_trace["stages_run"]
    assert "hiring_manager" not in result.generation_trace["stages_run"]


@pytest.mark.asyncio
async def test_bundle_audit_trail_carries_voice_fingerprint():
    """Audit trail includes voice_fingerprint_hash from the corpus."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda x: None
    application = _make_application()
    settings = _make_settings(daily_llm_cost_cap_usd=0.01)

    with patch(
        "services.document_generator.is_cost_capped",
        AsyncMock(return_value=True),
    ):
        result = await generate_bundle(session, application, settings=settings)

    # Pre-flight cap skip → corpus not assembled, hash stays None.
    assert result.generation_trace["voice_fingerprint_hash"] is None
    assert result.generation_trace["constitution_version"] == "v1"


def test_bundle_result_dataclass_defaults():
    r = BundleResult()
    assert r.resume is None
    assert r.screeners == []
    assert not r.degraded
    assert r.ethics is None
