"""Cover letter SOTA — adaptive format dispatch — plan 66 § T10."""

from __future__ import annotations

import pytest

from llm.prompts.draft_cover_letter_sota import (
    MAX_HOOK_CHARS,
    MAX_VERBATIM_PHRASES,
    CoverLetterSota,
    detect_pain_letter_format,
)


def test_detect_pain_letter_format_two_signals():
    """≥2 pain-point matches → True."""
    jd = "Looking to solve scale challenges in payments processing."
    assert detect_pain_letter_format(jd)


def test_detect_pain_letter_format_one_signal_returns_false():
    """One match is below the threshold."""
    jd = "We have challenges. The role builds new features."
    assert not detect_pain_letter_format(jd)


def test_detect_pain_letter_format_no_signal():
    jd = "Build infrastructure for our payment platform."
    assert not detect_pain_letter_format(jd)


def test_detect_pain_letter_format_handles_empty():
    assert not detect_pain_letter_format("")
    assert not detect_pain_letter_format(None or "")


def test_detect_pain_letter_format_case_insensitive():
    jd = "LOOKING TO SOLVE major Pain Points in our data stack."
    assert detect_pain_letter_format(jd)


def test_cover_letter_sota_schema_validates():
    letter = CoverLetterSota(
        format_chosen="standard",
        hook="Hook text.",
        match="Match section.",
        close="Close section.",
        hiring_manager_used={"name": "Jane", "source": "regex"},
        verbatim_phrases=["shipped the auth service"],
    )
    assert letter.format_chosen == "standard"
    assert letter.hiring_manager_used["name"] == "Jane"


def test_cover_letter_sota_format_literal():
    """format_chosen restricted to standard or pain_letter."""
    with pytest.raises(ValueError):
        CoverLetterSota(
            format_chosen="invalid_format",
            hook="x",
            match="x",
            close="x",
        )


def test_cover_letter_sota_section_caps_enforced():
    """hook ≤ MAX_HOOK_CHARS."""
    too_long = "x" * (MAX_HOOK_CHARS + 50)
    with pytest.raises(ValueError):
        CoverLetterSota(
            format_chosen="standard",
            hook=too_long,
            match="x",
            close="x",
        )


def test_cover_letter_sota_verbatim_phrase_cap():
    """verbatim_phrases capped at MAX_VERBATIM_PHRASES."""
    too_many = [f"phrase_{i}" for i in range(MAX_VERBATIM_PHRASES + 5)]
    with pytest.raises(ValueError):
        CoverLetterSota(
            format_chosen="standard",
            hook="x",
            match="x",
            close="x",
            verbatim_phrases=too_many,
        )


def test_cover_letter_sota_defaults():
    letter = CoverLetterSota(
        format_chosen="pain_letter",
        hook="h",
        match="m",
        close="c",
    )
    assert letter.hiring_manager_used == {"name": None, "source": None}
    assert letter.verbatim_phrases == []
