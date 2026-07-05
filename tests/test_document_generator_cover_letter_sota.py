"""generate_cover_letter switched to draft_cover_letter_sota — plan 66 § T10 (round-2 delta).

Architect REQUEST_CHANGES round 1: the SOTA prompt shipped but `generate_cover_letter`
still called `tracked_call(prompt_name="draft_cover_letter", ...)`. These tests
assert the active path is the SOTA prompt + the call goes through tracked_call
(closes hacker LOW-3 inline).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from services.generation import generate_cover_letter

pytestmark = pytest.mark.uses_sample_data_shims


def _make_settings(**overrides):
    base = {
        "user_id": 1,
        "llm_provider": "anthropic",
        "llm_model": "claude-sonnet-4-6",
        "daily_llm_cost_cap_usd": None,
        "cover_letter_format": "auto",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _make_application(**overrides):
    base = {
        "id": 42,
        "user_id": 1,
        "job_id": 100,
        "docs_state": None,
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
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _make_snap():
    return SimpleNamespace(
        profile=SimpleNamespace(
            full_name="Shyam Padia",
            summary_short="Senior engineer",
            summary_full="Long",
            email="x@y",
            phone="555",
            location="SF",
        ),
        experiences=[],
        bullets_by_experience={},
        skills=[],
        education=[],
        projects=[],
    )


@pytest.mark.asyncio
async def test_generate_cover_letter_uses_sota_prompt_name():
    """tracked_call must receive `prompt_name="draft_cover_letter_sota"`."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda x: None
    application = _make_application()
    settings = _make_settings()
    job = _make_job()

    captured: dict = {}

    async def _capture_tracked(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            value={
                "format_chosen": "standard",
                "hook": "Hook text.",
                "match": "Match section.",
                "close": "Close section.",
                "verbatim_phrases": ["shipped distributed"],
                "hiring_manager_used": {"name": "Jane", "source": "regex"},
            }
        )

    fake_compile = SimpleNamespace(
        byte_size=1234,
        page_count=1,
        compiled_at=datetime.now(UTC),
    )

    with (
        patch("services.generation.is_cost_capped", AsyncMock(return_value=False)),
        patch(
            "services.generation.load_profile_snapshot",
            AsyncMock(return_value=_make_snap()),
        ),
        patch("services.generation.get_provider"),
        patch("services.generation.llm_tracker.tracked_call", _capture_tracked),
        patch("services.generation.typst_compile", AsyncMock(return_value=fake_compile)),
        patch(
            "services.generation._app_documents_dir",
            return_value=Path("/tmp/app42"),
        ),
    ):
        doc = await generate_cover_letter(
            session,
            application,
            settings=settings,
            job=job,
            system="<preamble>",
            cache_system=True,
        )

    assert captured["prompt_name"] == "draft_cover_letter_sota"
    assert captured["system"] == "<preamble>"
    assert captured["cache_system"] is True
    # SOTA audit fields stashed in bullet_selection JSONB.
    assert doc.bullet_selection is not None
    assert doc.bullet_selection["format_chosen"] == "standard"
    assert "shipped distributed" in doc.bullet_selection["verbatim_phrases"]


@pytest.mark.asyncio
async def test_generate_cover_letter_pain_letter_dispatch():
    """JD with ≥2 pain-point signals → format_chosen='pain_letter'."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda x: None
    application = _make_application()
    settings = _make_settings()
    job = _make_job(
        description="Looking to solve scale challenges. We struggle with the data stack."
    )

    captured: dict = {}

    async def _capture_tracked(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            value={
                "format_chosen": "pain_letter",
                "hook": "h",
                "match": "m",
                "close": "c",
                "verbatim_phrases": [],
                "hiring_manager_used": {"name": None, "source": None},
            }
        )

    fake_compile = SimpleNamespace(byte_size=1, page_count=1, compiled_at=datetime.now(UTC))

    with (
        patch("services.generation.is_cost_capped", AsyncMock(return_value=False)),
        patch(
            "services.generation.load_profile_snapshot",
            AsyncMock(return_value=_make_snap()),
        ),
        patch("services.generation.get_provider"),
        patch("services.generation.llm_tracker.tracked_call", _capture_tracked),
        patch("services.generation.typst_compile", AsyncMock(return_value=fake_compile)),
        patch(
            "services.generation._app_documents_dir",
            return_value=Path("/tmp/app42"),
        ),
    ):
        await generate_cover_letter(session, application, settings=settings, job=job)

    # The pain-letter PROMPT_PAIN_LETTER template contains "PAIN-LETTER"
    assert "PAIN-LETTER" in captured["prompt"]
    assert "Looking to solve" in captured["prompt"] or "pain" in captured["prompt"].lower()


@pytest.mark.asyncio
async def test_generate_cover_letter_settings_override_pins_format():
    """Settings.cover_letter_format='standard' bypasses adaptive dispatch."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = lambda x: None
    application = _make_application()
    # Job has pain signals BUT settings pin standard
    settings = _make_settings(cover_letter_format="standard")
    job = _make_job(
        description="Looking to solve scale challenges. We struggle with the data stack."
    )

    captured: dict = {}

    async def _capture_tracked(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            value={
                "format_chosen": "standard",
                "hook": "h",
                "match": "m",
                "close": "c",
                "verbatim_phrases": [],
                "hiring_manager_used": {"name": None, "source": None},
            }
        )

    fake_compile = SimpleNamespace(byte_size=1, page_count=1, compiled_at=datetime.now(UTC))

    with (
        patch("services.generation.is_cost_capped", AsyncMock(return_value=False)),
        patch(
            "services.generation.load_profile_snapshot",
            AsyncMock(return_value=_make_snap()),
        ),
        patch("services.generation.get_provider"),
        patch("services.generation.llm_tracker.tracked_call", _capture_tracked),
        patch("services.generation.typst_compile", AsyncMock(return_value=fake_compile)),
        patch(
            "services.generation._app_documents_dir",
            return_value=Path("/tmp/app42"),
        ),
    ):
        await generate_cover_letter(session, application, settings=settings, job=job)

    # Standard template, not pain-letter
    assert "PAIN-LETTER" not in captured["prompt"]
    assert 'format_chosen="standard"' in captured["prompt"]
