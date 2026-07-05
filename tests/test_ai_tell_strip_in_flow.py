"""AI-tell strip_violations wired into bundle_generator post-LLM — plan 66 § T4 (round-2 delta).

Architect REQUEST_CHANGES round 1: `strip_violations` was tested standalone but never
invoked in the runtime flow. The bundle now scans resume trimmed bullets + cover-letter
sections post-LLM + records violations to `generation_trace.ai_tell_violations`.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from services.generation import generate_bundle
from services.voice_grounding import VoiceCorpus

pytestmark = pytest.mark.uses_sample_data_shims


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
        "skills_required": ["python"],
        "score": 0.30,
        "match_breakdown": {},
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _make_corpus():
    # Profile doesn't naturally use "delve" or "robust" or em-dashes; baseline.
    return VoiceCorpus(
        full_text="# Bullets\n- Shipped distributed platform.\n- Designed ML pipeline.",
        vocab_fingerprint=["distributed", "platform"],
        sentence_length_stats={"mean_words": 5.0, "std_dev_words": 0.0},
        idiomatic_phrases=[],
        voice_fingerprint_hash="sha256:test",
        source_counts={"bullets": 2},
    )


def _make_profile():
    return SimpleNamespace(
        id=99,
        user_id=1,
        full_name="Shyam Padia",
        headline="Senior Engineer",
        summary_full="Long",
        summary_short="Short",
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
async def test_bundle_records_em_dash_violations_from_resume_bullets():
    """LLM output containing em-dashes is detected by the post-LLM scan."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda x: None
    application = _make_application()
    settings = _make_settings()
    job = _make_job()

    # Resume trimmed_lines carry em-dashes (the single most common AI tell).
    fake_resume = SimpleNamespace(
        id=1,
        path="/tmp/r.pdf",
        bullet_selection={
            "selected_ids": [1, 2],
            "trimmed_lines": {
                "1": "Shipped the payment platform — scaled to 5M users.",
                "2": "Designed the ML pipeline — 50K rps.",
            },
        },
    )
    fake_cover = SimpleNamespace(id=2, path="/tmp/c.pdf", bullet_selection=None)
    fake_corpus = _make_corpus()
    fake_profile = _make_profile()

    session.exec = AsyncMock(
        return_value=SimpleNamespace(
            one_or_none=lambda: fake_profile,
            all=lambda: [(1,), (2,)],
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
            AsyncMock(return_value=None),
        ),
        patch(
            "services.document_generator.generate_resume",
            AsyncMock(return_value=fake_resume),
        ),
        patch(
            "services.generation._load_profile_experiences",
            AsyncMock(return_value=(fake_profile, [])),
        ),
        patch(
            "services.document_generator.generate_cover_letter",
            AsyncMock(return_value=fake_cover),
        ),
        patch(
            "services.document_generator.answer_screeners",
            AsyncMock(return_value=[]),
        ),
        patch(
            "services.generation.validate_parse_fidelity",
            return_value=None,
        ),
    ):
        result = await generate_bundle(session, application, settings=settings, job=job)

    assert "em-dash" in result.generation_trace["ai_tell_violations"]


@pytest.mark.asyncio
async def test_bundle_records_blocklist_violations_from_cover_letter_sections():
    """SOTA cover-letter sections containing blocklisted vocab show up in audit trail."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda x: None
    application = _make_application()
    settings = _make_settings()
    job = _make_job()

    fake_resume = SimpleNamespace(
        id=1,
        path="/tmp/r.pdf",
        bullet_selection={"selected_ids": [], "trimmed_lines": {}},
    )
    # Cover letter sections include AI-tell words (delve, leverage, robust).
    fake_cover = SimpleNamespace(
        id=2,
        path="/tmp/c.pdf",
        bullet_selection={
            "format_chosen": "standard",
            "hook": "I delve into distributed systems.",
            "match": "I leverage robust infrastructure.",
            "close": "I'd love to harness this opportunity.",
            "verbatim_phrases": [],
            "hiring_manager_used": {"name": None, "source": None},
        },
    )
    fake_corpus = _make_corpus()
    fake_profile = _make_profile()

    session.exec = AsyncMock(
        return_value=SimpleNamespace(
            one_or_none=lambda: fake_profile,
            all=lambda: [],
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
            AsyncMock(return_value=None),
        ),
        patch(
            "services.document_generator.generate_resume",
            AsyncMock(return_value=fake_resume),
        ),
        patch(
            "services.generation._load_profile_experiences",
            AsyncMock(return_value=(fake_profile, [])),
        ),
        patch(
            "services.document_generator.generate_cover_letter",
            AsyncMock(return_value=fake_cover),
        ),
        patch(
            "services.document_generator.answer_screeners",
            AsyncMock(return_value=[]),
        ),
        patch(
            "services.generation.validate_parse_fidelity",
            return_value=None,
        ),
    ):
        result = await generate_bundle(session, application, settings=settings, job=job)

    violations = set(result.generation_trace["ai_tell_violations"])
    # All four blocklisted words from the cover letter should appear.
    assert "delve" in violations
    assert "leverage" in violations
    assert "robust" in violations
    # harness/harnessing both match the bare verb; either form OK.
    assert any(v in violations for v in ("harness", "harnessing"))


@pytest.mark.asyncio
async def test_bundle_no_violations_when_text_clean():
    """No em-dash + no blocklist tokens → empty violations list."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda x: None
    application = _make_application()
    settings = _make_settings()
    job = _make_job()

    fake_resume = SimpleNamespace(
        id=1,
        path="/tmp/r.pdf",
        bullet_selection={
            "selected_ids": [1],
            "trimmed_lines": {"1": "Shipped payment platform to 5M users."},
        },
    )
    fake_cover = SimpleNamespace(id=2, path="/tmp/c.pdf", bullet_selection=None)
    fake_corpus = _make_corpus()
    fake_profile = _make_profile()

    session.exec = AsyncMock(
        return_value=SimpleNamespace(
            one_or_none=lambda: fake_profile,
            all=lambda: [(1,)],
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
            AsyncMock(return_value=None),
        ),
        patch(
            "services.document_generator.generate_resume",
            AsyncMock(return_value=fake_resume),
        ),
        patch(
            "services.generation._load_profile_experiences",
            AsyncMock(return_value=(fake_profile, [])),
        ),
        patch(
            "services.document_generator.generate_cover_letter",
            AsyncMock(return_value=fake_cover),
        ),
        patch(
            "services.document_generator.answer_screeners",
            AsyncMock(return_value=[]),
        ),
        patch(
            "services.generation.validate_parse_fidelity",
            return_value=None,
        ),
    ):
        result = await generate_bundle(session, application, settings=settings, job=job)

    assert result.generation_trace["ai_tell_violations"] == []
