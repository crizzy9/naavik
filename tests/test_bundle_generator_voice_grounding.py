"""Voice grounding wired into bundle_generator LLM calls — plan 66 § T2/T3 (round-2 delta).

Architect REQUEST_CHANGES round 1: the constitution preamble harness shipped in
the first PR turn but no callsite passed it as `system=`/`cache_system=True`.
These tests assert the preamble flows through to every LLM-bearing entry point
in the bundle pipeline.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from services.bundle_generator import generate_bundle
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
        "llm_model": "claude-3.5-sonnet-20250219",
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
        "description": "Build payment infrastructure with distributed systems.",
        "description_html": None,
        "skills_required": ["python", "go", "aws"],
        "score": 0.78,
        "match_breakdown": {},
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _make_corpus():
    return VoiceCorpus(
        full_text=(
            "# Bullets\n- Shipped distributed payment platform to 5M users.\n"
            "- Designed ML inference pipeline at 50K rps.\n"
            "# Profile summary\nSenior engineer focused on ML platforms."
        ),
        vocab_fingerprint=["distributed", "platform", "shipped"],
        sentence_length_stats={
            "mean_words": 10.0,
            "std_dev_words": 4.0,
            "short_pct": 30.0,
            "med_pct": 50.0,
            "long_pct": 20.0,
            "sentence_count": 5.0,
        },
        idiomatic_phrases=["payment platform"],
        voice_fingerprint_hash="sha256:abc",
        source_counts={"bullets": 5},
    )


def _make_profile():
    return SimpleNamespace(
        id=99,
        user_id=1,
        full_name="Shyam Padia",
        headline="Senior ML Engineer",
        summary_full="Long summary",
        summary_short="Short summary",
        email="x@y",
        phone="555",
        location="SF",
        portfolio_url=None,
        linkedin_handle=None,
        github_handle=None,
        work_authorization=None,
        deleted_at=None,
    )


@pytest.mark.asyncio
async def test_bundle_constitution_threaded_to_resume_call():
    """generate_resume must receive `system=<preamble>` + `cache_system=True`."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda x: None
    application = _make_application()
    settings = _make_settings()
    job = _make_job(score=0.30)  # below headline gate; skip headline LLM path

    fake_resume = SimpleNamespace(
        id=1,
        path="/tmp/resume.pdf",
        bullet_selection={"selected_ids": [1, 2], "trimmed_lines": {"1": "ok", "2": "good"}},
    )
    fake_cover = SimpleNamespace(id=2, path="/tmp/cover.pdf", bullet_selection=None)
    fake_corpus = _make_corpus()
    fake_profile = _make_profile()

    session.exec = AsyncMock(
        return_value=SimpleNamespace(
            one_or_none=lambda: fake_profile,
            all=lambda: [(1,), (2,)],
        )
    )

    captured_resume_kwargs: dict = {}

    async def _capture_resume(*args, **kwargs):
        captured_resume_kwargs.update(kwargs)
        return fake_resume

    with (
        patch(
            "services.bundle_generator.dg.is_cost_capped",
            AsyncMock(return_value=False),
        ),
        patch(
            "services.bundle_generator.assemble_corpus",
            AsyncMock(return_value=fake_corpus),
        ),
        patch(
            "services.bundle_generator.extract_hiring_manager",
            AsyncMock(return_value=None),
        ),
        patch(
            "services.bundle_generator.dg.generate_resume",
            _capture_resume,
        ),
        patch(
            "services.bundle_generator._load_profile_experiences",
            AsyncMock(return_value=(fake_profile, [])),
        ),
        patch(
            "services.bundle_generator.dg.generate_cover_letter",
            AsyncMock(return_value=fake_cover),
        ),
        patch(
            "services.bundle_generator.dg.answer_screeners",
            AsyncMock(return_value=[]),
        ),
        patch(
            "services.bundle_generator.validate_parse_fidelity",
            return_value=None,
        ),
    ):
        result = await generate_bundle(session, application, settings=settings, job=job)

    assert "system" in captured_resume_kwargs
    assert captured_resume_kwargs["system"] is not None
    assert "Shyam Padia" in captured_resume_kwargs["system"]
    assert captured_resume_kwargs["cache_system"] is True
    assert result.generation_trace["constitution_present"] is True


@pytest.mark.asyncio
async def test_bundle_constitution_threaded_to_cover_letter_call():
    """generate_cover_letter receives the constitution preamble + matched_tags."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda x: None
    application = _make_application()
    settings = _make_settings()
    job = _make_job(score=0.30, match_breakdown={"matched_tags": ["python", "distributed"]})

    fake_resume = SimpleNamespace(
        id=1,
        path="/tmp/resume.pdf",
        bullet_selection={"selected_ids": [], "trimmed_lines": {}},
    )
    fake_cover = SimpleNamespace(id=2, path="/tmp/cover.pdf", bullet_selection=None)
    fake_corpus = _make_corpus()
    fake_profile = _make_profile()
    fake_hm = HiringManagerHit(name="Jane Smith", title="EM", source="regex", confidence=0.9)

    session.exec = AsyncMock(
        return_value=SimpleNamespace(
            one_or_none=lambda: fake_profile,
            all=lambda: [],
        )
    )

    captured_cover_kwargs: dict = {}

    async def _capture_cover(*args, **kwargs):
        captured_cover_kwargs.update(kwargs)
        return fake_cover

    with (
        patch(
            "services.bundle_generator.dg.is_cost_capped",
            AsyncMock(return_value=False),
        ),
        patch(
            "services.bundle_generator.assemble_corpus",
            AsyncMock(return_value=fake_corpus),
        ),
        patch(
            "services.bundle_generator.extract_hiring_manager",
            AsyncMock(return_value=fake_hm),
        ),
        patch(
            "services.bundle_generator.dg.generate_resume",
            AsyncMock(return_value=fake_resume),
        ),
        patch(
            "services.bundle_generator._load_profile_experiences",
            AsyncMock(return_value=(fake_profile, [])),
        ),
        patch(
            "services.bundle_generator.dg.generate_cover_letter",
            _capture_cover,
        ),
        patch(
            "services.bundle_generator.dg.answer_screeners",
            AsyncMock(return_value=[]),
        ),
        patch(
            "services.bundle_generator.validate_parse_fidelity",
            return_value=None,
        ),
    ):
        await generate_bundle(session, application, settings=settings, job=job)

    assert "system" in captured_cover_kwargs
    assert captured_cover_kwargs["system"] is not None
    assert captured_cover_kwargs["cache_system"] is True
    assert captured_cover_kwargs.get("hiring_manager") is not None
    assert captured_cover_kwargs["hiring_manager"]["name"] == "Jane Smith"
    assert captured_cover_kwargs.get("matched_tags") == ["python", "distributed"]


@pytest.mark.asyncio
async def test_bundle_constitution_threaded_to_headline_call():
    """tailor_headline_for_application receives constitution preamble."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda x: None
    application = _make_application()
    settings = _make_settings()
    job = _make_job(score=0.78, match_breakdown={"matched_tags": ["ml"]})

    fake_resume = SimpleNamespace(id=1, path="/tmp/r.pdf", bullet_selection=None)
    fake_cover = SimpleNamespace(id=2, path="/tmp/c.pdf", bullet_selection=None)
    fake_corpus = _make_corpus()
    fake_profile = _make_profile()

    session.exec = AsyncMock(
        return_value=SimpleNamespace(
            one_or_none=lambda: fake_profile,
            all=lambda: [],
        )
    )

    captured_headline_kwargs: dict = {}

    async def _capture_headline(*args, **kwargs):
        captured_headline_kwargs.update(kwargs)
        return None

    with (
        patch(
            "services.bundle_generator.dg.is_cost_capped",
            AsyncMock(return_value=False),
        ),
        patch(
            "services.bundle_generator.assemble_corpus",
            AsyncMock(return_value=fake_corpus),
        ),
        patch(
            "services.bundle_generator.extract_hiring_manager",
            AsyncMock(return_value=None),
        ),
        patch(
            "services.bundle_generator.dg.generate_resume",
            AsyncMock(return_value=fake_resume),
        ),
        patch(
            "services.bundle_generator._load_profile_experiences",
            AsyncMock(return_value=(fake_profile, [])),
        ),
        patch(
            "services.bundle_generator.tailor_headline_for_application",
            _capture_headline,
        ),
        patch(
            "services.bundle_generator.dg.generate_cover_letter",
            AsyncMock(return_value=fake_cover),
        ),
        patch(
            "services.bundle_generator.dg.answer_screeners",
            AsyncMock(return_value=[]),
        ),
        patch(
            "services.bundle_generator.validate_parse_fidelity",
            return_value=None,
        ),
    ):
        await generate_bundle(session, application, settings=settings, job=job)

    assert "system" in captured_headline_kwargs
    assert captured_headline_kwargs["system"] is not None
    assert captured_headline_kwargs["cache_system"] is True


@pytest.mark.asyncio
async def test_bundle_no_constitution_when_no_corpus():
    """Cold-start user (no Profile / no corpus) → preamble stays None; cache_system=False."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda x: None
    application = _make_application()
    settings = _make_settings()
    job = _make_job(score=0.30)  # skip headline gate

    fake_resume = SimpleNamespace(id=1, path="/tmp/r.pdf", bullet_selection=None)
    fake_cover = SimpleNamespace(id=2, path="/tmp/c.pdf", bullet_selection=None)
    # Empty corpus — no profile / no bullets / etc.
    empty_corpus = VoiceCorpus(
        full_text="",
        vocab_fingerprint=[],
        sentence_length_stats={},
        idiomatic_phrases=[],
        voice_fingerprint_hash="sha256:empty",
        source_counts={},
    )

    session.exec = AsyncMock(
        return_value=SimpleNamespace(
            one_or_none=lambda: None,
            all=lambda: [],
        )
    )

    captured_resume_kwargs: dict = {}

    async def _capture_resume(*args, **kwargs):
        captured_resume_kwargs.update(kwargs)
        return fake_resume

    with (
        patch(
            "services.bundle_generator.dg.is_cost_capped",
            AsyncMock(return_value=False),
        ),
        patch(
            "services.bundle_generator.assemble_corpus",
            AsyncMock(return_value=empty_corpus),
        ),
        patch(
            "services.bundle_generator.extract_hiring_manager",
            AsyncMock(return_value=None),
        ),
        patch(
            "services.bundle_generator.dg.generate_resume",
            _capture_resume,
        ),
        patch(
            "services.bundle_generator._load_profile_experiences",
            AsyncMock(return_value=(None, [])),  # cold-start: no Profile
        ),
        patch(
            "services.bundle_generator.dg.generate_cover_letter",
            AsyncMock(return_value=fake_cover),
        ),
        patch(
            "services.bundle_generator.dg.answer_screeners",
            AsyncMock(return_value=[]),
        ),
        patch(
            "services.bundle_generator.validate_parse_fidelity",
            return_value=None,
        ),
    ):
        result = await generate_bundle(session, application, settings=settings, job=job)

    assert captured_resume_kwargs.get("system") is None
    assert captured_resume_kwargs.get("cache_system") is False
    assert result.generation_trace["constitution_present"] is False
