"""Burstiness check_and_score wired into bundle_generator — plan 66 § T5 (round-2 delta).

Architect REQUEST_CHANGES round 1: `check_and_score` was tested standalone but never
invoked in the runtime flow. The bundle now records `burstiness_std` to the audit
trail. The one-shot REGEN of the worst offender is deferred to 0.3.3 (requires a
bullet-id-targeted retrim surface in document_generator that does not yet exist).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from services.bundle_generator import generate_bundle
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
        "description": "Build payment infrastructure.",
        "description_html": None,
        "skills_required": ["python"],
        "score": 0.30,
        "match_breakdown": {},
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _make_corpus():
    return VoiceCorpus(
        full_text="# Bullets\n- Shipped distributed platform.",
        vocab_fingerprint=["distributed"],
        sentence_length_stats={"mean_words": 5.0, "std_dev_words": 0.0},
        idiomatic_phrases=[],
        voice_fingerprint_hash="sha256:test",
        source_counts={"bullets": 1},
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


async def _run_bundle(session, application, settings, job, fake_resume):
    fake_cover = SimpleNamespace(id=2, path="/tmp/c.pdf", bullet_selection=None)
    fake_corpus = _make_corpus()
    fake_profile = _make_profile()

    session.exec = AsyncMock(
        return_value=SimpleNamespace(
            one_or_none=lambda: fake_profile,
            all=lambda: [(i,) for i in range(20)],
        )
    )

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
        return await generate_bundle(session, application, settings=settings, job=job)


@pytest.mark.asyncio
async def test_bundle_records_low_burstiness_when_bullets_uniform():
    """Uniform-length trimmed bullets → low std-dev → recorded to audit trail."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda x: None
    application = _make_application()
    settings = _make_settings()
    job = _make_job()

    # All bullets exactly 6 words → zero variance, well below threshold.
    uniform_bullets = {
        "1": "shipped the payment platform to users",
        "2": "designed the ML pipeline at scale",
        "3": "led the data team across geos",
        "4": "built the model serving at rate",
    }
    fake_resume = SimpleNamespace(
        id=1,
        path="/tmp/r.pdf",
        bullet_selection={
            "selected_ids": [1, 2, 3, 4],
            "trimmed_lines": uniform_bullets,
        },
    )

    result = await _run_bundle(session, application, settings, job, fake_resume)

    # burstiness_std is recorded (non-None, low value).
    assert result.generation_trace["burstiness_std"] is not None
    assert result.generation_trace["burstiness_std"] < 6.0


@pytest.mark.asyncio
async def test_bundle_records_high_burstiness_when_bullets_varied():
    """Varied-length bullets → high std-dev → audit trail captures pass signal."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda x: None
    application = _make_application()
    settings = _make_settings()
    job = _make_job()

    # Bullets with markedly different word counts → high variance.
    varied_bullets = {
        "1": "shipped it",
        "2": "designed the ML inference pipeline serving 50K requests per second across three regions",
        "3": "built tools",
        "4": (
            "led a cross-functional team that delivered the new payment platform after deeply "
            "redesigning the distributed transaction layer for greater throughput"
        ),
    }
    fake_resume = SimpleNamespace(
        id=1,
        path="/tmp/r.pdf",
        bullet_selection={
            "selected_ids": [1, 2, 3, 4],
            "trimmed_lines": varied_bullets,
        },
    )

    result = await _run_bundle(session, application, settings, job, fake_resume)

    assert result.generation_trace["burstiness_std"] is not None
    assert result.generation_trace["burstiness_std"] >= 6.0


@pytest.mark.asyncio
async def test_bundle_skips_burstiness_when_one_bullet():
    """<2 bullets → no variance signal; burstiness_std stays None or zero-ish."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda x: None
    application = _make_application()
    settings = _make_settings()
    job = _make_job()

    one_bullet = {"1": "shipped the payment platform"}
    fake_resume = SimpleNamespace(
        id=1,
        path="/tmp/r.pdf",
        bullet_selection={"selected_ids": [1], "trimmed_lines": one_bullet},
    )

    result = await _run_bundle(session, application, settings, job, fake_resume)

    # check_and_score is guarded by `len(trimmed) >= 2` so std stays at initial None.
    assert result.generation_trace["burstiness_std"] is None
