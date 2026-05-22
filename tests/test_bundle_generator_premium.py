"""PREMIUM-tier bundle dispatch tests — plan 67 (0.3.4) § C.6 / T8 / T13 / T14.

Covers:
- tier="free" path unchanged (backward-compat regression gate per T13)
- tier="premium" routes through _generate_bundle_premium
- PREMIUM happy path: council + detector + critique + tool_loop all run
- Cost-cap mid-flight: FREE composite ships + PREMIUM stages skipped
- Audit trail carries PREMIUM keys
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from services.bundle_generator import (
    BundleResult,
    generate_bundle,
)

pytestmark = pytest.mark.uses_sample_data_shims


def _settings(**overrides):
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
        "generation_tier": "free",
        "originality_api_key": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _application(**overrides):
    base = {
        "id": 42,
        "user_id": 1,
        "job_id": 100,
        "company": "Stripe",
        "role": "Sr Engineer",
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


@pytest.mark.asyncio
async def test_free_tier_default_routes_to_free_path():
    """When generation_tier='free', tier kwarg='free', the free flow runs.

    Backward-compat regression gate per T13 — FREE callers see no change.
    """
    settings = _settings(generation_tier="free", daily_llm_cost_cap_usd=0.01)
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda x: None
    app = _application()

    with patch(
        "services.bundle_generator.dg.is_cost_capped",
        AsyncMock(return_value=True),
    ):
        result = await generate_bundle(session, app, settings=settings)

    assert result.degraded is True
    assert result.skipped_reason == "cost_cap_reached"
    assert result.generation_trace["tier"] == "free"


@pytest.mark.asyncio
async def test_premium_tier_explicit_kwarg_overrides_settings():
    """An explicit tier='premium' kwarg overrides settings.generation_tier."""
    settings = _settings(generation_tier="free", daily_llm_cost_cap_usd=0.01)
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda x: None
    app = _application()

    with patch(
        "services.bundle_generator._generate_bundle_premium",
        AsyncMock(
            return_value=BundleResult(
                degraded=False,
                generation_trace={"tier": "premium", "premium_stages_completed": []},
            )
        ),
    ) as mock_premium:
        result = await generate_bundle(session, app, settings=settings, tier="premium")

    mock_premium.assert_awaited_once()
    assert result.generation_trace["tier"] == "premium"


@pytest.mark.asyncio
async def test_settings_generation_tier_premium_dispatches():
    """When Settings.generation_tier='premium' and no explicit tier kwarg,
    the premium branch runs."""
    settings = _settings(generation_tier="premium")
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda x: None
    app = _application()

    with patch(
        "services.bundle_generator._generate_bundle_premium",
        AsyncMock(return_value=BundleResult(generation_trace={"tier": "premium"})),
    ) as mock_premium:
        result = await generate_bundle(session, app, settings=settings)

    mock_premium.assert_awaited_once()
    assert result.generation_trace["tier"] == "premium"


@pytest.mark.asyncio
async def test_premium_cost_cap_pre_flight_falls_back_to_free_skipped():
    """When cost cap fires before any stage, the PREMIUM dispatcher
    inherits the FREE skipped_reason without exploding."""
    from services.bundle_generator import _generate_bundle_premium

    settings = _settings(generation_tier="premium", daily_llm_cost_cap_usd=0.01)
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda x: None
    app = _application()

    with patch(
        "services.bundle_generator.dg.is_cost_capped",
        AsyncMock(return_value=True),
    ):
        result = await _generate_bundle_premium(session, app, settings=settings)

    assert result.degraded is True
    assert result.skipped_reason == "cost_cap_reached"
    # Trace preserves PREMIUM tier label so the audit trail clearly reads
    # "PREMIUM bundle that exited pre-flight"
    assert result.generation_trace["tier"] == "premium"


@pytest.mark.asyncio
async def test_premium_happy_path_calls_all_4_stages():
    """End-to-end PREMIUM call wires council + detector + critique + tool_loop."""
    from services.bundle_generator import _generate_bundle_premium
    from services.council import SelectedBullets
    from services.critique_council import CritiqueReport
    from services.detector_loop import DetectorReport
    from services.tool_loop import IterationRecord, ToolLoopReport

    settings = _settings(generation_tier="premium")
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda x: None
    app = _application()

    free_result = BundleResult(
        resume=SimpleNamespace(
            path="/tmp/resume.pdf",
            bullet_selection={
                "selected_ids": [1, 2, 3],
                "trimmed_lines": {"1": "did x", "2": "shipped y", "3": "led z"},
            },
        ),
        cover_letter=SimpleNamespace(
            path="/tmp/cover.pdf",
            bullet_selection={"hook": "hello", "match": "matched", "close": "thanks"},
        ),
        generation_trace={"tier": "free", "stages_run": ["corpus"], "total_cost_usd": 0.1},
    )

    council_report = SelectedBullets(
        selected_ids=[1, 2, 3],
        persona_rankings={"pragmatic_recruiter": [1, 2, 3]},
        borda_scores={1: 9, 2: 6, 3: 3},
    )
    detector_report = DetectorReport(
        final_text="text",
        final_confidence=0.15,
        target_met=True,
        iterations=[],
        originality_score=0.1,
    )
    critique_report = CritiqueReport(
        persona_votes=[{"persona": "faang_l5_l6_hm", "concerns": [], "recommendation": "ship"}],
        consensus_concerns=[],
        recommendation_tally={"ship": 3, "revise": 0, "reject": 0},
        majority_recommendation="ship",
        should_regenerate=False,
    )
    tool_report = ToolLoopReport(
        final_decision="ship",
        iterations=[IterationRecord(iter_n=0, decision="ship", cost_usd=0.04)],
    )

    with (
        patch(
            "services.bundle_generator.generate_bundle",
            AsyncMock(return_value=free_result),
        ),
        patch(
            "services.bundle_generator.dg.is_cost_capped",
            AsyncMock(return_value=False),
        ),
        patch(
            "services.bundle_generator.assemble_corpus",
            AsyncMock(return_value=None),
        ),
        patch(
            "services.bundle_generator._load_profile_experiences",
            AsyncMock(return_value=(None, [])),
        ),
        patch(
            "services.council.vote_on_bullet_selection",
            AsyncMock(return_value=council_report),
        ),
        patch(
            "services.detector_loop.run_detector_loop",
            AsyncMock(return_value=detector_report),
        ),
        patch(
            "services.critique_council.critique_bundle",
            AsyncMock(return_value=critique_report),
        ),
        patch(
            "services.tool_loop.orchestrate_refinement",
            AsyncMock(return_value=tool_report),
        ),
    ):
        # Application has no job_id set so we need to set one
        app.job_id = 100
        session.exec = AsyncMock(
            return_value=SimpleNamespace(
                one_or_none=lambda: SimpleNamespace(
                    id=100,
                    description="job desc",
                    description_html="",
                    role="Eng",
                    skills_required=["python"],
                    company="Stripe",
                    match_breakdown={},
                ),
                all=lambda: [],
            )
        )
        result = await _generate_bundle_premium(session, app, settings=settings)

    trace = result.generation_trace
    assert trace["tier"] == "premium"
    assert "council_votes" in trace
    assert trace["council_selected_ids"] == [1, 2, 3]
    assert "detector_final_confidence" in trace
    assert trace["originality_score"] == 0.1
    assert "critique_persona_feedback" in trace
    assert trace["critique_majority_recommendation"] == "ship"
    assert "tool_loop_iterations" in trace
    assert trace["tool_loop_final_decision"] == "ship"
    assert "council" in trace["premium_stages_completed"]
    assert "detector" in trace["premium_stages_completed"]
    assert "critique" in trace["premium_stages_completed"]
    assert "tool_loop" in trace["premium_stages_completed"]


@pytest.mark.asyncio
async def test_premium_cost_cap_mid_flight_skips_remaining_stages():
    """Cost cap firing between PREMIUM stages skips downstream + flags degraded."""
    from services.bundle_generator import _generate_bundle_premium
    from services.council import SelectedBullets

    settings = _settings(generation_tier="premium")
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda x: None
    app = _application()
    app.job_id = 100

    free_result = BundleResult(
        resume=SimpleNamespace(
            path="/tmp/resume.pdf",
            bullet_selection={
                "selected_ids": [1],
                "trimmed_lines": {"1": "x"},
            },
        ),
        cover_letter=None,
        generation_trace={"tier": "free", "stages_run": [], "total_cost_usd": 0.0},
    )

    council_report = SelectedBullets(selected_ids=[1], persona_rankings={}, borda_scores={1: 1})

    # Sequence: pre-PREMIUM cost-cap False, then True before detector
    cost_cap_seq = [False, True]  # iter 0: pre-council pass; iter 1: pre-detector fail
    cap_call_count = {"i": 0}

    async def _cap(*args, **kwargs):
        i = cap_call_count["i"]
        cap_call_count["i"] += 1
        return cost_cap_seq[i] if i < len(cost_cap_seq) else True

    with (
        patch(
            "services.bundle_generator.generate_bundle",
            AsyncMock(return_value=free_result),
        ),
        patch(
            "services.bundle_generator.dg.is_cost_capped",
            new=AsyncMock(side_effect=_cap),
        ),
        patch(
            "services.bundle_generator.assemble_corpus",
            AsyncMock(return_value=None),
        ),
        patch(
            "services.bundle_generator._load_profile_experiences",
            AsyncMock(return_value=(None, [])),
        ),
        patch(
            "services.council.vote_on_bullet_selection",
            AsyncMock(return_value=council_report),
        ),
    ):
        session.exec = AsyncMock(
            return_value=SimpleNamespace(
                one_or_none=lambda: SimpleNamespace(
                    id=100,
                    description="x",
                    description_html="",
                    role="Eng",
                    skills_required=[],
                    company="Stripe",
                    match_breakdown={},
                ),
                all=lambda: [],
            )
        )
        result = await _generate_bundle_premium(session, app, settings=settings)

    trace = result.generation_trace
    assert trace["tier"] == "premium"
    assert trace.get("degraded_mode") is True
    assert trace.get("degraded_reason") == "cost_cap_reached_premium"
    # Council completed; detector/critique/tool_loop skipped
    assert "council" in trace["premium_stages_completed"]
    for skipped in ("detector", "critique", "tool_loop"):
        assert skipped in trace["premium_stages_skipped"]
    assert result.degraded is True


@pytest.mark.asyncio
async def test_premium_inherits_free_trace_fields():
    """PREMIUM merges all FREE trace keys + adds PREMIUM keys without dropping."""
    from services.bundle_generator import _generate_bundle_premium

    settings = _settings(generation_tier="premium", daily_llm_cost_cap_usd=0.01)
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda x: None
    app = _application()

    # FREE skipped due to cap; we just verify the trace structure inheritance.
    with patch(
        "services.bundle_generator.dg.is_cost_capped",
        AsyncMock(return_value=True),
    ):
        result = await _generate_bundle_premium(session, app, settings=settings)

    assert result.generation_trace["tier"] == "premium"
    # FREE trace fields preserved
    assert "schema_version" in result.generation_trace
    assert "stages_run" in result.generation_trace
    # PREMIUM-only audit fields initialized
    assert "premium_stages_completed" in result.generation_trace
    assert "premium_stages_skipped" in result.generation_trace


# ── PR #168 round-2: ensemble_score must be invoked from PREMIUM dispatch ──


@pytest.mark.asyncio
async def test_premium_invokes_ensemble_score_and_records_trace_keys(tmp_path):
    """Architect HIGH-1 regression: `ensemble_score` MUST be called from
    `_generate_bundle_premium` when the rendered PDF exists. The audit trail
    MUST carry `ensemble_parse_score` + `ensemble_parsers_used` keys."""
    from services.ats_parser_ensemble import EnsembleReport
    from services.bundle_generator import _generate_bundle_premium
    from services.council import SelectedBullets
    from services.critique_council import CritiqueReport
    from services.detector_loop import DetectorReport
    from services.tool_loop import IterationRecord, ToolLoopReport

    # Real on-disk PDF stub so Path.exists() returns True
    pdf_path = tmp_path / "resume.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")

    settings = _settings(generation_tier="premium")
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda x: None
    app = _application()
    app.job_id = 100

    free_result = BundleResult(
        resume=SimpleNamespace(
            path=str(pdf_path),
            bullet_selection={
                "selected_ids": [1, 2],
                "trimmed_lines": {"1": "did x", "2": "shipped y"},
            },
        ),
        cover_letter=SimpleNamespace(
            path="/tmp/cover.pdf",
            bullet_selection={"hook": "hello", "match": "matched"},
        ),
        generation_trace={"tier": "free", "stages_run": [], "total_cost_usd": 0.05},
    )

    ensemble_report = EnsembleReport(
        aggregate_score=0.89,
        pdfplumber_score=0.88,
        pyresparser_score=0.90,
        openresume_score=None,
        parsers_used=["pdfplumber", "pyresparser"],
        fields_found={"name": True, "email": True},
        notes=["openresume unavailable"],
    )

    council_report = SelectedBullets(
        selected_ids=[1, 2],
        persona_rankings={"pragmatic_recruiter": [1, 2]},
        borda_scores={1: 6, 2: 3},
    )
    detector_report = DetectorReport(
        final_text="text",
        final_confidence=0.15,
        target_met=True,
        iterations=[],
        originality_score=0.1,
    )
    critique_report = CritiqueReport(
        persona_votes=[{"persona": "faang_l5_l6_hm", "concerns": [], "recommendation": "ship"}],
        consensus_concerns=[],
        recommendation_tally={"ship": 3, "revise": 0, "reject": 0},
        majority_recommendation="ship",
        should_regenerate=False,
    )
    tool_report = ToolLoopReport(
        final_decision="ship",
        iterations=[IterationRecord(iter_n=0, decision="ship", cost_usd=0.04)],
    )

    with (
        patch(
            "services.bundle_generator.generate_bundle",
            AsyncMock(return_value=free_result),
        ),
        patch(
            "services.bundle_generator.dg.is_cost_capped",
            AsyncMock(return_value=False),
        ),
        patch(
            "services.bundle_generator.assemble_corpus",
            AsyncMock(return_value=None),
        ),
        patch(
            "services.bundle_generator._load_profile_experiences",
            AsyncMock(return_value=(None, [])),
        ),
        patch(
            "services.council.vote_on_bullet_selection",
            AsyncMock(return_value=council_report),
        ),
        patch(
            "services.detector_loop.run_detector_loop",
            AsyncMock(return_value=detector_report),
        ),
        patch(
            "services.ats_parser_ensemble.ensemble_score",
            AsyncMock(return_value=ensemble_report),
        ) as mock_ensemble,
        patch(
            "services.critique_council.critique_bundle",
            AsyncMock(return_value=critique_report),
        ),
        patch(
            "services.tool_loop.orchestrate_refinement",
            AsyncMock(return_value=tool_report),
        ),
    ):
        session.exec = AsyncMock(
            return_value=SimpleNamespace(
                one_or_none=lambda: SimpleNamespace(
                    id=100,
                    description="job desc",
                    description_html="",
                    role="Eng",
                    skills_required=[],
                    company="Stripe",
                    match_breakdown={},
                ),
                all=lambda: [],
            )
        )
        result = await _generate_bundle_premium(session, app, settings=settings)

    # The ensemble MUST have been called — this is the dead-code regression guard
    mock_ensemble.assert_awaited_once()
    # Trace keys MUST be present per plan T10
    trace = result.generation_trace
    assert trace["ensemble_parse_score"] == 0.89
    assert trace["ensemble_parsers_used"] == ["pdfplumber", "pyresparser"]
    assert "ensemble" in trace["premium_stages_completed"]
    # Below-threshold flag computed correctly (0.89 >= 0.75 = not below)
    assert trace["ensemble_below_threshold"] is False


@pytest.mark.asyncio
async def test_premium_ensemble_below_threshold_records_warning_flag():
    """Sub-threshold ensemble score sets `ensemble_below_threshold=True` for
    UI surfacing without triggering mid-flight regen (deferred to user motion)."""
    import os
    import tempfile

    from services.ats_parser_ensemble import EnsembleReport
    from services.bundle_generator import _generate_bundle_premium

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(b"%PDF-1.4 fake")
        pdf_path = tmp.name

    try:
        settings = _settings(generation_tier="premium", parse_fidelity_threshold=0.75)
        session = AsyncMock()
        session.flush = AsyncMock()
        session.add = lambda x: None
        app = _application()
        app.job_id = 100

        free_result = BundleResult(
            resume=SimpleNamespace(
                path=pdf_path,
                bullet_selection={"selected_ids": [], "trimmed_lines": {}},
            ),
            cover_letter=None,
            generation_trace={"tier": "free", "stages_run": [], "total_cost_usd": 0.0},
        )

        below_threshold = EnsembleReport(
            aggregate_score=0.55,
            pdfplumber_score=0.55,
            pyresparser_score=None,
            openresume_score=None,
            parsers_used=["pdfplumber"],
            fields_found={},
            notes=[],
        )

        with (
            patch(
                "services.bundle_generator.generate_bundle",
                AsyncMock(return_value=free_result),
            ),
            patch(
                "services.bundle_generator.dg.is_cost_capped",
                AsyncMock(return_value=False),
            ),
            patch(
                "services.bundle_generator.assemble_corpus",
                AsyncMock(return_value=None),
            ),
            patch(
                "services.bundle_generator._load_profile_experiences",
                AsyncMock(return_value=(None, [])),
            ),
            patch(
                "services.ats_parser_ensemble.ensemble_score",
                AsyncMock(return_value=below_threshold),
            ) as mock_ensemble,
        ):
            session.exec = AsyncMock(
                return_value=SimpleNamespace(
                    one_or_none=lambda: SimpleNamespace(
                        id=100,
                        description="",
                        description_html="",
                        role="Eng",
                        skills_required=[],
                        company="Stripe",
                        match_breakdown={},
                    ),
                    all=lambda: [],
                )
            )
            result = await _generate_bundle_premium(session, app, settings=settings)

        mock_ensemble.assert_awaited_once()
        trace = result.generation_trace
        assert trace["ensemble_parse_score"] == 0.55
        assert trace["ensemble_below_threshold"] is True
    finally:
        os.unlink(pdf_path)


@pytest.mark.asyncio
async def test_premium_ensemble_skipped_when_pdf_missing():
    """No PDF on disk (FREE pipeline didn't render) -> ensemble in skipped."""
    from services.bundle_generator import _generate_bundle_premium

    settings = _settings(generation_tier="premium")
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda x: None
    app = _application()
    app.job_id = 100

    free_result = BundleResult(
        resume=SimpleNamespace(
            path="/tmp/nonexistent-resume.pdf",
            bullet_selection={"selected_ids": [], "trimmed_lines": {}},
        ),
        cover_letter=None,
        generation_trace={"tier": "free", "stages_run": [], "total_cost_usd": 0.0},
    )

    with (
        patch(
            "services.bundle_generator.generate_bundle",
            AsyncMock(return_value=free_result),
        ),
        patch(
            "services.bundle_generator.dg.is_cost_capped",
            AsyncMock(return_value=False),
        ),
        patch(
            "services.bundle_generator.assemble_corpus",
            AsyncMock(return_value=None),
        ),
        patch(
            "services.bundle_generator._load_profile_experiences",
            AsyncMock(return_value=(None, [])),
        ),
        patch(
            "services.ats_parser_ensemble.ensemble_score",
            AsyncMock(),
        ) as mock_ensemble,
    ):
        session.exec = AsyncMock(
            return_value=SimpleNamespace(
                one_or_none=lambda: SimpleNamespace(
                    id=100,
                    description="",
                    description_html="",
                    role="Eng",
                    skills_required=[],
                    company="Stripe",
                    match_breakdown={},
                ),
                all=lambda: [],
            )
        )
        result = await _generate_bundle_premium(session, app, settings=settings)

    # ensemble MUST NOT be called when PDF is missing
    mock_ensemble.assert_not_called()
    trace = result.generation_trace
    assert "ensemble" in trace["premium_stages_skipped"]
    assert "ensemble_parse_score" not in trace
