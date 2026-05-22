"""Hiring manager extractor — plan 66 (0.3.1) § T11."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from services.hiring_manager_extractor import (
    HiringManagerHit,
    _try_regex,
    extract_hiring_manager,
)

pytestmark = pytest.mark.uses_sample_data_shims


def test_regex_picks_up_hiring_manager_explicit():
    desc = "We're a tight team. Hiring Manager: Jane Smith. You'll join product."
    hit = _try_regex(desc)
    assert hit is not None
    assert hit.name == "Jane Smith"
    assert hit.source == "regex"
    assert hit.confidence == 0.90


def test_regex_picks_up_reporting_to():
    desc = "The role reports up through engineering. Reporting to Bob Marley directly."
    hit = _try_regex(desc)
    assert hit is not None
    assert hit.name == "Bob Marley"


def test_regex_picks_up_youll_report_to():
    desc = "You'll report to Mary Jones in this position."
    hit = _try_regex(desc)
    assert hit is not None
    assert hit.name == "Mary Jones"


def test_regex_misses_generic_team():
    desc = "Hiring Team is excited about this role. Apply via portal."
    hit = _try_regex(desc)
    assert hit is None


def test_regex_misses_empty_description():
    assert _try_regex("") is None
    assert _try_regex(None or "") is None


@pytest.mark.asyncio
async def test_manual_override_shortcircuits():
    session = AsyncMock()
    settings = SimpleNamespace()
    hit = await extract_hiring_manager(
        session=session,
        user_id=1,
        settings=settings,
        job_description="Any job description",
        manual_override="Alice Custom",
    )
    assert hit is not None
    assert hit.name == "Alice Custom"
    assert hit.source == "manual"
    assert hit.confidence == 1.0


@pytest.mark.asyncio
async def test_manual_override_strips_whitespace():
    session = AsyncMock()
    settings = SimpleNamespace()
    hit = await extract_hiring_manager(
        session=session,
        user_id=1,
        settings=settings,
        job_description="x",
        manual_override="  Alice  ",
    )
    assert hit.name == "Alice"


@pytest.mark.asyncio
async def test_blank_manual_override_falls_through():
    session = AsyncMock()
    settings = SimpleNamespace()
    hit = await extract_hiring_manager(
        session=session,
        user_id=1,
        settings=settings,
        job_description="Generic team hiring",
        manual_override="   ",
    )
    # Falls through; regex misses + JD <200 → None.
    assert hit is None


@pytest.mark.asyncio
async def test_regex_hit_skips_llm_fallback():
    session = AsyncMock()
    settings = SimpleNamespace()
    with patch("services.hiring_manager_extractor.get_provider") as mock_provider:
        hit = await extract_hiring_manager(
            session=session,
            user_id=1,
            settings=settings,
            job_description="Hiring Manager: Pat Day. " + "x" * 300,
        )
        assert hit is not None
        assert hit.source == "regex"
        mock_provider.assert_not_called()


@pytest.mark.asyncio
async def test_short_jd_skips_llm_fallback():
    session = AsyncMock()
    settings = SimpleNamespace()
    with patch("services.hiring_manager_extractor.get_provider") as mock_provider:
        hit = await extract_hiring_manager(
            session=session,
            user_id=1,
            settings=settings,
            job_description="Short JD. Apply now.",  # <200 chars, no regex hit
        )
        assert hit is None
        mock_provider.assert_not_called()


def test_hit_dataclass_shape():
    hit = HiringManagerHit(
        name="Test",
        title="Manager",
        source="regex",
        confidence=0.9,
    )
    assert hit.name == "Test"
    assert hit.confidence == 0.9
