"""Settings · Generation tab tests — plan 67 (0.3.4) § C.6 / T7 / T14.

Covers:
- compute_premium_cost_projection: history-based when >=10 PREMIUM bundles
- compute_premium_cost_projection: ROADMAP fallback when 0 history
- update_generation persists tier + originality + tier_2_evasion
- list_recent_generation_traces filters + caps at limit
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from services.settings import (
    _PREMIUM_PROJECTION_FALLBACK,
    CostProjection,
    compute_premium_cost_projection,
    list_recent_generation_traces,
    update_generation,
)

pytestmark = pytest.mark.uses_sample_data_shims


@pytest.mark.asyncio
async def test_cost_projection_fallback_when_no_history():
    """0 PREMIUM bundles → return ROADMAP fallback projection."""
    session = AsyncMock()
    session.exec = AsyncMock(return_value=SimpleNamespace(all=lambda: []))
    proj = await compute_premium_cost_projection(session, user_id=1)
    assert proj == _PREMIUM_PROJECTION_FALLBACK
    assert proj.from_history is False
    assert proj.total_usd == 0.61


@pytest.mark.asyncio
async def test_cost_projection_history_based_when_enough_samples():
    """>=10 PREMIUM bundles → averaged per-stage projection."""
    session = AsyncMock()

    # 10 PREMIUM applications + corresponding ApiUsage rows
    app_rows = [(i, {"tier": "premium", "stages_run": []}) for i in range(1, 11)]
    # Each premium app has 0.05 detector + 0.05 council + 0.10 tool_loop
    usage_rows = []
    for app_id in range(1, 11):
        usage_rows.extend(
            [
                (app_id, "detect_ai_likelihood", 0.05),
                (app_id, "council_pragmatic_recruiter_batch", 0.05),
                (app_id, "orchestrate_refinement_iter_0", 0.10),
            ]
        )

    session.exec = AsyncMock(
        side_effect=[
            SimpleNamespace(all=lambda: app_rows),
            SimpleNamespace(all=lambda: usage_rows),
        ]
    )

    proj = await compute_premium_cost_projection(session, user_id=1)

    assert isinstance(proj, CostProjection)
    assert proj.from_history is True
    assert proj.sample_size == 10
    assert proj.detector_usd == 0.05
    assert proj.council_usd == 0.05
    assert proj.tool_loop_usd == 0.10
    assert proj.total_usd == pytest.approx(0.20, abs=1e-3)


@pytest.mark.asyncio
async def test_cost_projection_skips_free_bundles():
    """Applications with tier='free' are NOT counted toward PREMIUM history."""
    session = AsyncMock()
    app_rows = [(i, {"tier": "free"}) for i in range(1, 20)]
    session.exec = AsyncMock(return_value=SimpleNamespace(all=lambda: app_rows))
    proj = await compute_premium_cost_projection(session, user_id=1)
    assert proj.from_history is False


@pytest.mark.asyncio
async def test_update_generation_persists_tier_toggle():
    """PUT /api/v1/settings/generation with tier='premium' persists."""
    session = AsyncMock()
    session.flush = AsyncMock()
    fake_settings = SimpleNamespace(
        user_id=1,
        generation_tier="free",
        originality_api_key=None,
        tier_2_evasion_enabled=False,
        ai_writing_voice_samples="",
        cover_letter_format="auto",
        resume_template_preference="auto",
        parse_fidelity_threshold=0.75,
        updated_at=None,
    )
    session.add = lambda r: None

    with patch(
        "services.settings.get_or_create",
        AsyncMock(return_value=fake_settings),
    ):
        s = await update_generation(
            session,
            user_id=1,
            generation_tier="premium",
        )
    assert s.generation_tier == "premium"


@pytest.mark.asyncio
async def test_update_generation_rejects_invalid_tier():
    """generation_tier outside {free, premium} raises ValueError."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda r: None
    fake = SimpleNamespace(
        user_id=1,
        generation_tier="free",
        originality_api_key=None,
        tier_2_evasion_enabled=False,
        ai_writing_voice_samples="",
        cover_letter_format="auto",
        resume_template_preference="auto",
        parse_fidelity_threshold=0.75,
        updated_at=None,
    )
    with (
        patch(
            "services.settings.get_or_create",
            AsyncMock(return_value=fake),
        ),
        pytest.raises(ValueError, match="generation_tier"),
    ):
        await update_generation(session, user_id=1, generation_tier="enterprise")


@pytest.mark.asyncio
async def test_update_generation_persists_originality_key():
    """Originality API key persists; empty string preserves existing (regression
    guard for the silent-wipe bug — form re-submit always sends `""` because
    the password input has no `value=`). To clear, callers pass the explicit
    `originality_api_key_clear=True` sentinel."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda r: None
    fake = SimpleNamespace(
        user_id=1,
        generation_tier="free",
        originality_api_key="old-key",
        tier_2_evasion_enabled=False,
        ai_writing_voice_samples="",
        cover_letter_format="auto",
        resume_template_preference="auto",
        parse_fidelity_threshold=0.75,
        updated_at=None,
    )

    # New non-empty value: set
    with patch(
        "services.settings.get_or_create",
        AsyncMock(return_value=fake),
    ):
        s = await update_generation(session, user_id=1, originality_api_key="sk-new")
    assert s.originality_api_key == "sk-new"

    # Empty string + no clear sentinel: PRESERVE existing (regression guard)
    fake.originality_api_key = "sk-new"
    with patch(
        "services.settings.get_or_create",
        AsyncMock(return_value=fake),
    ):
        s = await update_generation(session, user_id=1, originality_api_key="")
    assert s.originality_api_key == "sk-new"

    # Explicit clear sentinel: drop to None
    with patch(
        "services.settings.get_or_create",
        AsyncMock(return_value=fake),
    ):
        s = await update_generation(
            session,
            user_id=1,
            originality_api_key="",
            originality_api_key_clear=True,
        )
    assert s.originality_api_key is None


@pytest.mark.asyncio
async def test_update_generation_preserves_originality_when_field_absent():
    """Plan 67 round-2 regression: form save without re-entering the API key
    (the common path, since the password input never echoes existing value)
    MUST leave the stored key untouched."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda r: None
    fake = SimpleNamespace(
        user_id=1,
        generation_tier="free",
        originality_api_key="sk-existing",
        tier_2_evasion_enabled=False,
        ai_writing_voice_samples="",
        cover_letter_format="auto",
        resume_template_preference="auto",
        parse_fidelity_threshold=0.75,
        updated_at=None,
    )

    # Caller toggles tier_2_evasion only; originality_api_key not in payload
    with patch(
        "services.settings.get_or_create",
        AsyncMock(return_value=fake),
    ):
        s = await update_generation(
            session,
            user_id=1,
            tier_2_evasion_enabled=True,
        )
    assert s.originality_api_key == "sk-existing"
    assert s.tier_2_evasion_enabled is True

    # Caller submits empty originality_api_key (form auto-blank) — preserves
    with patch(
        "services.settings.get_or_create",
        AsyncMock(return_value=fake),
    ):
        s = await update_generation(
            session,
            user_id=1,
            originality_api_key="",
            tier_2_evasion_enabled=False,
        )
    assert s.originality_api_key == "sk-existing"
    assert s.tier_2_evasion_enabled is False


@pytest.mark.asyncio
async def test_update_generation_tier_2_evasion_partial_skip():
    """tier_2_evasion_enabled=None → field stays untouched (partial PUT idiom)."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda r: None
    fake = SimpleNamespace(
        user_id=1,
        generation_tier="free",
        originality_api_key=None,
        tier_2_evasion_enabled=True,  # previously enabled
        ai_writing_voice_samples="",
        cover_letter_format="auto",
        resume_template_preference="auto",
        parse_fidelity_threshold=0.75,
        updated_at=None,
    )

    with patch(
        "services.settings.get_or_create",
        AsyncMock(return_value=fake),
    ):
        s = await update_generation(session, user_id=1)  # no kwargs
    assert s.tier_2_evasion_enabled is True


@pytest.mark.asyncio
async def test_list_recent_generation_traces_returns_premium_keys():
    """Audit-trail viewer query returns full trace for each app."""
    session = AsyncMock()
    rows = [
        (
            42,
            "Stripe",
            "Sr Eng",
            None,
            {
                "tier": "premium",
                "council_votes": {"pragmatic_recruiter": [1, 2, 3]},
                "detector_iterations": [{"iter_n": 0, "confidence": 0.2}],
            },
        ),
        (
            41,
            "Anthropic",
            "Eng",
            None,
            {"tier": "free", "stages_run": ["corpus"]},
        ),
    ]
    session.exec = AsyncMock(return_value=SimpleNamespace(all=lambda: rows))
    traces = await list_recent_generation_traces(session, user_id=1, limit=20)
    assert len(traces) == 2
    assert traces[0]["application_id"] == 42
    assert traces[0]["tier"] == "premium"
    assert "council_votes" in traces[0]["trace"]
    assert traces[1]["tier"] == "free"


@pytest.mark.asyncio
async def test_list_recent_generation_traces_handles_session_none():
    """list_recent_generation_traces returns [] when session is None."""
    # (settings_service requires a real session)
    result = await list_recent_generation_traces(None, user_id=1, limit=10)
    assert result == []
