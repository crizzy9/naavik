"""AI-tell blocklist enforcement — plan 66 (0.3.1) § T4."""

from __future__ import annotations

from services.ai_tell_blocklist import (
    BAKED_IN_BLOCKLIST,
    effective_blocklist,
    strip_violations,
)


def test_baked_in_blocklist_size_meets_minimum():
    # Plan locks 30 baked-in entries.
    assert len(BAKED_IN_BLOCKLIST) >= 30


def test_em_dash_is_replaced_with_comma_or_period():
    text = "I shipped this — and it worked."
    scrubbed, violations = strip_violations(text)
    assert "—" not in scrubbed
    assert "em-dash" in violations
    # Mid-sentence em-dash → ", "
    assert "this, and" in scrubbed.lower() or "this. And" in scrubbed


def test_em_dash_at_sentence_boundary_becomes_period():
    text = "Built the auth flow — Then handled the rollout."
    scrubbed, violations = strip_violations(text)
    assert "—" not in scrubbed
    assert "em-dash" in violations
    # Sentence boundary em-dash → ". "
    assert "flow. Then" in scrubbed


def test_blocklist_word_is_stripped_and_recorded():
    text = "We leveraged a robust system to underscore the value."
    scrubbed, violations = strip_violations(text)
    # Both `leveraged`, `robust`, `underscore` are in the blocklist
    assert "leveraged" in violations
    assert "robust" in violations
    assert "underscore" in violations
    assert "leveraged" not in scrubbed.lower()
    assert "robust" not in scrubbed.lower()
    assert "underscore" not in scrubbed.lower()


def test_blocklist_case_insensitive():
    text = "We LEVERAGED our system."
    scrubbed, violations = strip_violations(text)
    assert "leverage" in violations or "leveraged" in violations
    assert "leveraged" not in scrubbed.lower()


def test_multi_word_blocklist_phrases_are_caught():
    text = "In conclusion, the system works."
    scrubbed, violations = strip_violations(text)
    assert "in conclusion" in violations
    assert "in conclusion" not in scrubbed.lower()


def test_clean_text_returns_empty_violations():
    text = "I shipped the auth service. It cut latency from 80ms to 12ms."
    scrubbed, violations = strip_violations(text)
    assert violations == []
    assert scrubbed == text


def test_effective_blocklist_subtracts_user_natural_vocab():
    # User naturally uses "leverage" — should be removed from blocklist.
    corpus = "I leverage my background in distributed systems to ship value."
    active = effective_blocklist(corpus)
    assert "leverage" not in active
    # Words the user does NOT use stay in the active blocklist.
    assert "delve" in active


def test_effective_blocklist_with_none_returns_full_set():
    assert effective_blocklist(None) == set(BAKED_IN_BLOCKLIST)
    assert effective_blocklist("") == set(BAKED_IN_BLOCKLIST)


def test_strip_violations_with_custom_blocklist():
    custom = {"customword"}
    scrubbed, violations = strip_violations("We used customword here.", custom)
    assert "customword" in violations
    assert "customword" not in scrubbed.lower()
