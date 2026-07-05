"""Bundle generator — `bullet_selection_log` trace shape (plan 72 / 0.3.2.02).

Verifies the new `Application.generation_trace.bullet_selection_log` key the
Discover · review inline rationale UI reads from. Additive to the existing
`bullet_selections` shape (which existing readers still consume).

Shape:
    [{"bullet_id": int, "selected": bool, "why_selected": str|null, "why_dropped": str|null}]
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from services.generation import generate_bundle
from services.generation.ats_parser_fidelity import ParseScoreReport
from services.generation.hiring_manager_extractor import HiringManagerHit
from services.generation.voice_grounding import VoiceCorpus


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
        "user_id": 1,
        "company": "Stripe",
        "role": "Senior Engineer",
        "score": 0.78,
        "description": "We need a senior engineer.",
        "description_html": None,
        "match_breakdown": {"matched_tags": ["ai-ml"]},
        "skills_required": ["python", "ml"],
        "board": None,
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
async def test_bullet_selection_log_initialized_in_initial_trace() -> None:
    """Pre-flight cost-cap skip path: `bullet_selection_log` initialized as []."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda x: None
    application = _make_application()
    settings = _make_settings(daily_llm_cost_cap_usd=0.01)

    with patch(
        "services.generation.is_cost_capped",
        AsyncMock(return_value=True),
    ):
        result = await generate_bundle(session, application, settings=settings)

    trace = result.generation_trace
    assert "bullet_selection_log" in trace
    assert trace["bullet_selection_log"] == []
    # `bullet_selections` stays initialized too (no regression).
    assert "bullet_selections" in trace
    assert trace["bullet_selections"] == []


@pytest.mark.asyncio
async def test_bullet_selection_log_populated_for_selected_bullets() -> None:
    """Resume materializes → log entries per selected_id with the plan-72 shape."""
    session = AsyncMock()
    session.exec = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda x: None
    application = _make_application()
    settings = _make_settings()
    job = _make_job()

    fake_resume = SimpleNamespace(
        id=1,
        path="/tmp/resume.pdf",
        bullet_selection={
            "selected_ids": [7, 12, 18],
            "trimmed_lines": {"7": "a", "12": "b", "18": "c"},
        },
    )
    fake_cover = SimpleNamespace(id=2, path="/tmp/cover.pdf", bullet_selection=None)
    fake_hm = HiringManagerHit(name="Jane", title=None, source="regex", confidence=0.9)

    # Stub session.exec for the ethics-stage Bullet.id collection.
    bullet_rows = [(7,), (12,), (18,)]
    session.exec = AsyncMock(
        return_value=SimpleNamespace(
            one_or_none=lambda: SimpleNamespace(id=1, user_id=1),
            all=lambda: bullet_rows,
        )
    )

    with (
        patch(
            "services.generation.is_cost_capped",
            AsyncMock(return_value=False),
        ),
        patch(
            "services.generation.assemble_corpus",
            AsyncMock(return_value=_make_corpus()),
        ),
        patch(
            "services.generation.extract_hiring_manager",
            AsyncMock(return_value=fake_hm),
        ),
        patch(
            "services.generation.generate_resume",
            AsyncMock(return_value=fake_resume),
        ),
        patch(
            # Mirror test_bundle_generator.py — skip preamble + headline by
            # returning (None, []) so the test focuses on the resume → trace
            # bullet_selection_log shape.
            "services.generation._load_profile_experiences",
            AsyncMock(return_value=(None, [])),
        ),
        patch(
            "services.generation.generate_cover_letter",
            AsyncMock(return_value=fake_cover),
        ),
        patch(
            "services.generation.answer_screeners",
            AsyncMock(return_value=[]),
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

    trace = result.generation_trace
    log = trace["bullet_selection_log"]
    assert len(log) == 3
    # Per-entry shape — every key present, types correct.
    for entry, expected_id in zip(log, [7, 12, 18], strict=True):
        assert set(entry.keys()) == {"bullet_id", "selected", "why_selected", "why_dropped"}
        assert entry["bullet_id"] == expected_id
        assert entry["selected"] is True
        assert entry["why_selected"] is None
        assert entry["why_dropped"] is None
    # bullet_selections (legacy reader) still produced.
    assert len(trace["bullet_selections"]) == 3


@pytest.mark.asyncio
async def test_bullet_selection_log_dedupes_duplicate_ids() -> None:
    """Duplicate selected_ids do not produce duplicate log entries."""
    session = AsyncMock()
    session.exec = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda x: None
    application = _make_application()
    settings = _make_settings()
    job = _make_job()

    fake_resume = SimpleNamespace(
        id=1,
        path="/tmp/resume.pdf",
        bullet_selection={
            "selected_ids": [7, 7, 12, 12, 18],  # duplicates
            "trimmed_lines": {"7": "a", "12": "b", "18": "c"},
        },
    )
    fake_cover = SimpleNamespace(id=2, path="/tmp/cover.pdf", bullet_selection=None)
    fake_hm = HiringManagerHit(name="Jane", title=None, source="regex", confidence=0.9)

    session.exec = AsyncMock(
        return_value=SimpleNamespace(
            one_or_none=lambda: SimpleNamespace(id=1, user_id=1),
            all=lambda: [(7,), (12,), (18,)],
        )
    )

    with (
        patch(
            "services.generation.is_cost_capped",
            AsyncMock(return_value=False),
        ),
        patch(
            "services.generation.assemble_corpus",
            AsyncMock(return_value=_make_corpus()),
        ),
        patch(
            "services.generation.extract_hiring_manager",
            AsyncMock(return_value=fake_hm),
        ),
        patch(
            "services.generation.generate_resume",
            AsyncMock(return_value=fake_resume),
        ),
        patch(
            "services.generation._load_profile_experiences",
            AsyncMock(return_value=(None, [])),
        ),
        patch(
            "services.generation.generate_cover_letter",
            AsyncMock(return_value=fake_cover),
        ),
        patch(
            "services.generation.answer_screeners",
            AsyncMock(return_value=[]),
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

    log = result.generation_trace["bullet_selection_log"]
    # Dedup'd: 3 entries, not 5.
    assert len(log) == 3
    assert [e["bullet_id"] for e in log] == [7, 12, 18]
