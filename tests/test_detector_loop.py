"""Adversarial detector loop tests — plan 67 (0.3.4) § C.1 / T14.

Covers convergence at iter 0, refine cycle, iter cap, OriginalityProvider
mock + graceful no-key, and budget-aware early exit.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from services.generation.detector_loop import (
    DEFAULT_TARGET_CONFIDENCE,
    DetectorReport,
    run_detector_loop,
)

pytestmark = pytest.mark.uses_sample_data_shims


def _settings(**overrides):
    base = {
        "user_id": 1,
        "llm_provider": "anthropic",
        "llm_model": "claude-sonnet-4-6",
        "daily_llm_cost_cap_usd": None,
        "originality_api_key": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _verdict(conf: float, phrases: list[str] | None = None, rationale: str = ""):
    return SimpleNamespace(
        value={
            "ai_confidence": conf,
            "flagged_phrases": phrases or [],
            "rationale": rationale,
        }
    )


def _refined(rewritten: str, changes: list[str] | None = None):
    return SimpleNamespace(value={"rewritten": rewritten, "changes": changes or []})


@pytest.mark.asyncio
async def test_empty_input_short_circuits():
    """Empty text returns immediately; no LLM call fires."""
    settings = _settings()
    with patch("services.generation.detector_loop.get_provider"):
        report = await run_detector_loop(
            "",
            session=None,
            user_id=1,
            settings=settings,
        )
    assert isinstance(report, DetectorReport)
    assert report.final_text == ""
    assert report.target_met is True
    assert report.early_exit_reason == "empty_input"
    assert report.iterations == []


@pytest.mark.asyncio
async def test_iter_0_convergence_no_refine():
    """Text scoring below target on first detect → no refine pass, no
    originality call."""
    settings = _settings(originality_api_key="sk-test")
    session = AsyncMock()

    fake_provider = SimpleNamespace(provider_id="anthropic")
    detect_call = AsyncMock(return_value=_verdict(0.10, []))
    originality_call = AsyncMock(return_value=0.05)

    with (
        patch("services.generation.detector_loop.get_provider", return_value=fake_provider),
        patch(
            "services.generation.detector_loop.llm_tracker.tracked_call",
            detect_call,
        ),
        patch(
            "services.generation.detector_loop.originality_score_text",
            originality_call,
        ),
        patch(
            "services.generation.is_cost_capped",
            AsyncMock(return_value=False),
        ),
    ):
        report = await run_detector_loop(
            "human-sounding text",
            session=session,
            user_id=1,
            settings=settings,
        )

    assert report.target_met is True
    assert report.final_confidence == 0.10
    assert len(report.iterations) == 1
    assert report.iterations[0].iter_n == 0
    assert report.iterations[0].refinements == []
    # No refine happened → originality skipped
    assert originality_call.await_count == 0
    assert report.originality_score is None


@pytest.mark.asyncio
async def test_refine_then_converge_calls_originality():
    """One refine pass drops confidence; convergence triggers originality."""
    settings = _settings(originality_api_key="sk-test")
    session = AsyncMock()

    fake_provider = SimpleNamespace(provider_id="anthropic")

    # Sequence: iter 0 detect 0.85 + phrases → refine → iter 1 detect 0.18.
    call_log: list[str] = []

    async def tracked(*args, **kwargs):
        prompt_name = kwargs.get("prompt_name")
        call_log.append(prompt_name)
        if prompt_name == "detect_ai_likelihood":
            if call_log.count("detect_ai_likelihood") == 1:
                return _verdict(0.85, ["leverage robust", "comprehensive"], "smells AI")
            return _verdict(0.18, [], "much better")
        if prompt_name == "refine_to_human":
            return _refined("refined text", ["leverage robust -> use", "comprehensive -> full"])
        raise AssertionError(f"unexpected prompt: {prompt_name}")

    with (
        patch("services.generation.detector_loop.get_provider", return_value=fake_provider),
        patch("services.generation.detector_loop.llm_tracker.tracked_call", new=tracked),
        patch(
            "services.generation.detector_loop.originality_score_text",
            AsyncMock(return_value=0.12),
        ),
        patch(
            "services.generation.is_cost_capped",
            AsyncMock(return_value=False),
        ),
    ):
        report = await run_detector_loop(
            "this leverage robust comprehensive blah",
            session=session,
            user_id=1,
            settings=settings,
            target_confidence=DEFAULT_TARGET_CONFIDENCE,
        )

    assert report.target_met is True
    assert report.final_text == "refined text"
    assert len(report.iterations) == 2
    assert report.iterations[0].confidence == 0.85
    assert len(report.iterations[0].refinements) == 2
    assert report.iterations[1].confidence == 0.18
    assert report.originality_score == 0.12


@pytest.mark.asyncio
async def test_max_iters_cap_exits_with_last_attempt():
    """When confidence stays above target across 3 iters, return last attempt
    + target_met=False; final iteration doesn't refine (last text retained)."""
    settings = _settings()
    session = AsyncMock()

    # Always returns high confidence + phrases — never converges
    async def tracked(*args, **kwargs):
        prompt_name = kwargs.get("prompt_name")
        if prompt_name == "detect_ai_likelihood":
            return _verdict(0.78, ["X", "Y"], "still smells")
        return _refined("refined again", ["X -> A", "Y -> B"])

    with (
        patch(
            "services.generation.detector_loop.get_provider",
            return_value=SimpleNamespace(provider_id="anthropic"),
        ),
        patch("services.generation.detector_loop.llm_tracker.tracked_call", new=tracked),
        patch(
            "services.generation.is_cost_capped",
            AsyncMock(return_value=False),
        ),
    ):
        report = await run_detector_loop(
            "stubborn AI text",
            session=session,
            user_id=1,
            settings=settings,
            max_iters=3,
        )

    assert report.target_met is False
    assert report.final_confidence == 0.78
    assert len(report.iterations) == 3


@pytest.mark.asyncio
async def test_budget_early_exit_no_llm_call():
    """When cost-cap fires before iter 0, no LLM call happens + early_exit
    reason is recorded."""
    settings = _settings(daily_llm_cost_cap_usd=0.01)
    session = AsyncMock()
    detect_call = AsyncMock()

    with (
        patch("services.generation.detector_loop.get_provider", return_value=SimpleNamespace()),
        patch("services.generation.detector_loop.llm_tracker.tracked_call", detect_call),
        patch(
            "services.generation.is_cost_capped",
            AsyncMock(return_value=True),
        ),
    ):
        report = await run_detector_loop(
            "any text",
            session=session,
            user_id=1,
            settings=settings,
        )

    assert report.early_exit_reason == "cost_cap_reached"
    assert report.iterations == []
    assert detect_call.await_count == 0


@pytest.mark.asyncio
async def test_no_api_key_skips_originality():
    """Even after a refine pass, missing originality_api_key → score is None."""
    settings = _settings(originality_api_key=None)
    session = AsyncMock()

    sequence = [
        _verdict(0.7, ["X"]),
        _refined("refined"),
        _verdict(0.15),
    ]
    idx = {"i": 0}

    async def tracked(*args, **kwargs):
        ret = sequence[idx["i"]]
        idx["i"] += 1
        return ret

    originality_call = AsyncMock(return_value=0.5)

    with (
        patch("services.generation.detector_loop.get_provider", return_value=SimpleNamespace()),
        patch("services.generation.detector_loop.llm_tracker.tracked_call", new=tracked),
        patch(
            "services.generation.detector_loop.originality_score_text",
            originality_call,
        ),
        patch(
            "services.generation.is_cost_capped",
            AsyncMock(return_value=False),
        ),
    ):
        report = await run_detector_loop(
            "AI text",
            session=session,
            user_id=1,
            settings=settings,
        )

    assert report.target_met is True
    assert report.originality_score is None
    assert originality_call.await_count == 0


@pytest.mark.asyncio
async def test_originality_provider_no_key_returns_none():
    """OriginalityProvider with no api_key returns None on score_text."""
    from llm.providers.originality import OriginalityProvider

    provider = OriginalityProvider(api_key=None)
    assert provider.configured is False
    assert await provider.score_text("some text") is None


@pytest.mark.asyncio
async def test_originality_score_text_helper_no_key():
    """`originality.score_text` returns None + persists no row when key absent."""
    from llm.providers.originality import score_text

    session = AsyncMock()
    result = await score_text(
        text="any",
        api_key=None,
        session=session,
        user_id=1,
    )
    assert result is None
    # No row persisted — provider.configured is False, helper short-circuits.
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_originality_score_text_persists_on_success():
    """Successful Originality call persists an ApiUsage row + returns score."""
    from llm.providers import originality

    session = AsyncMock()
    session.flush = AsyncMock()
    added = []
    session.add = lambda row: added.append(row)

    fake_provider = SimpleNamespace(
        configured=True,
        score_text=AsyncMock(return_value=0.42),
    )

    with patch.object(originality, "OriginalityProvider", return_value=fake_provider):
        score = await originality.score_text(
            text="some text",
            api_key="sk-test",
            session=session,
            user_id=1,
            application_id=99,
        )

    assert score == 0.42
    assert len(added) == 1
    row = added[0]
    assert row.user_id == 1
    assert row.application_id == 99
    assert row.prompt_name == "originality_ai_scan"
    assert row.cost_usd == originality.COST_PER_SCAN_USD
    assert row.succeeded is True


@pytest.mark.asyncio
async def test_originality_score_text_persists_on_failure():
    """When the upstream call returns None (HTTP error), row still persists
    with succeeded=False + cost=0."""
    from llm.providers import originality

    session = AsyncMock()
    session.flush = AsyncMock()
    added = []
    session.add = lambda row: added.append(row)

    fake_provider = SimpleNamespace(
        configured=True,
        score_text=AsyncMock(return_value=None),
    )

    with patch.object(originality, "OriginalityProvider", return_value=fake_provider):
        score = await originality.score_text(
            text="some text",
            api_key="sk-test",
            session=session,
            user_id=1,
        )

    assert score is None
    assert len(added) == 1
    row = added[0]
    assert row.succeeded is False
    assert row.cost_usd == 0.0
    assert row.error_kind == "originality_unavailable"
