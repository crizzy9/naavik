"""Voice corpus assembly + stats — plan 66 (0.3.1) § T1."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.voice_grounding import (
    VoiceCorpus,
    assemble_corpus,
    compute_sentence_stats,
    compute_vocab_fingerprint,
    extract_idiomatic_phrases,
    voice_fingerprint_hash,
)

pytestmark = pytest.mark.uses_sample_data_shims


def test_compute_sentence_stats_handles_empty_corpus():
    stats = compute_sentence_stats("")
    assert stats["mean_words"] == 0.0
    assert stats["sentence_count"] == 0.0


def test_compute_sentence_stats_classifies_short_medium_long():
    corpus = (
        "I shipped it. "  # 3 words = short
        "We rebuilt the payment service from the ground up. "  # 10 words = medium
        "Then I designed a new event-stream pipeline that processed millions of "
        "records per hour while handling failure gracefully without dropping "
        "any payload across the entire migration window. "  # ≥20 words = long
    )
    stats = compute_sentence_stats(corpus)
    assert stats["sentence_count"] == 3
    assert stats["short_pct"] > 0
    assert stats["med_pct"] > 0
    assert stats["long_pct"] > 0


def test_compute_vocab_fingerprint_drops_stopwords_and_short_tokens():
    text = "I rebuilt the data pipeline. I rebuilt the pipeline again."
    tokens = compute_vocab_fingerprint(text, top_n=5)
    # `rebuilt` + `pipeline` are non-stopword; `i`/`the` are stopwords.
    assert "rebuilt" in tokens
    assert "pipeline" in tokens
    assert "i" not in tokens
    assert "the" not in tokens


def test_extract_idiomatic_phrases_returns_repeated_bigrams():
    text = "Built data pipeline. Built data pipeline twice. Built data pipeline thrice."
    phrases = extract_idiomatic_phrases(text)
    assert any("built data" in p or "data pipeline" in p for p in phrases)


def test_voice_fingerprint_hash_is_deterministic():
    h1 = voice_fingerprint_hash("hello world", "v1")
    h2 = voice_fingerprint_hash("hello world", "v1")
    assert h1 == h2
    assert h1.startswith("sha256:")
    assert len(h1) == len("sha256:") + 32


def test_voice_fingerprint_hash_changes_with_blocklist_version():
    h1 = voice_fingerprint_hash("hello world", "v1")
    h2 = voice_fingerprint_hash("hello world", "v2")
    assert h1 != h2


def test_voice_fingerprint_hash_changes_with_corpus():
    h1 = voice_fingerprint_hash("hello world", "v1")
    h2 = voice_fingerprint_hash("goodbye world", "v1")
    assert h1 != h2


@pytest.mark.asyncio
async def test_assemble_corpus_aggregates_all_five_sources(monkeypatch):
    """When all 5 sources have content, the corpus contains all of them."""
    # Mock the per-source loaders directly — keeps the test independent of
    # SQLModel pagination + JOIN syntax.
    from services import voice_grounding as vg

    async def _bullets(*args, **kwargs):
        return ["shipped the auth service", "drove latency from 80ms to 12ms"]

    async def _summaries(*args, **kwargs):
        return ["Senior backend engineer with 8+ years."]

    async def _answers(*args, **kwargs):
        return ["I'm interested in distributed systems and ML platforms."]

    async def _samples(*args, **kwargs):
        return ["I prefer concrete numbers over qualitative claims."]

    async def _past(*args, **kwargs):
        return ["Built payment service from scratch"]

    monkeypatch.setattr(vg, "_bullet_texts", _bullets)
    monkeypatch.setattr(vg, "_profile_summaries", _summaries)
    monkeypatch.setattr(vg, "_profile_answers", _answers)
    monkeypatch.setattr(vg, "_settings_voice_samples", _samples)
    monkeypatch.setattr(vg, "_past_trimmed_lines", _past)

    session = SimpleNamespace()
    corpus = await assemble_corpus(session, user_id=1)
    assert isinstance(corpus, VoiceCorpus)
    assert "# Bullets" in corpus.full_text
    assert "# Profile summary" in corpus.full_text
    assert "# Past screener answers" in corpus.full_text
    assert "# User voice samples" in corpus.full_text
    assert "# Past trimmed lines" in corpus.full_text
    assert corpus.source_counts["bullets"] == 2
    assert corpus.source_counts["voice_samples"] == 1
    assert corpus.source_counts["past_trimmed_lines"] == 1
    assert corpus.voice_fingerprint_hash.startswith("sha256:")
    assert len(corpus.vocab_fingerprint) > 0


@pytest.mark.asyncio
async def test_assemble_corpus_handles_missing_sources(monkeypatch):
    """No profile / no bullets returns empty-but-valid corpus."""
    from services import voice_grounding as vg

    async def _empty(*args, **kwargs):
        return []

    monkeypatch.setattr(vg, "_bullet_texts", _empty)
    monkeypatch.setattr(vg, "_profile_summaries", _empty)
    monkeypatch.setattr(vg, "_profile_answers", _empty)
    monkeypatch.setattr(vg, "_settings_voice_samples", _empty)
    monkeypatch.setattr(vg, "_past_trimmed_lines", _empty)

    session = SimpleNamespace()
    corpus = await assemble_corpus(session, user_id=99)
    assert corpus.full_text == ""
    assert corpus.vocab_fingerprint == []
    assert corpus.source_counts == {
        "bullets": 0,
        "summaries": 0,
        "profile_answers": 0,
        "voice_samples": 0,
        "past_trimmed_lines": 0,
    }
