"""Voice grounding corpus assembly — plan 66 (0.3.1) § T1.

Composes a per-user voice corpus from five sources:

1. `Bullet.text` rows (full set across all experiences).
2. `Profile.summary_full` + `Profile.summary_short`.
3. `ProfileAnswer.answer` rows (per-user screener reuse cache).
4. `Settings.ai_writing_voice_samples` (free-form supplemental samples).
5. Past `GeneratedDocument.bullet_selection.trimmed_lines` (reinforcement).

The result is rendered into the constitution preamble (T3) so every LLM
call in the bundle pipeline is anchored to the candidate's actual voice.
Stats are computed with stdlib only — no `textstat` dep this PR.

`voice_fingerprint_hash` derives from the corpus + blocklist version;
when bullets/profile/samples mutate, the hash changes, and Anthropic's
ephemeral prompt cache auto-invalidates the prefix (T2).
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from statistics import mean, pstdev

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import (
    Bullet,
    Experience,
    GeneratedDocument,
    Profile,
    ProfileAnswer,
    Settings,
)

# Stop-words filtered out of the vocab fingerprint so the top-N tokens
# carry voice signal, not English-baseline frequency. Lowercase, alpha-only.
_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "if",
        "then",
        "of",
        "to",
        "in",
        "on",
        "at",
        "by",
        "for",
        "with",
        "as",
        "from",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "i",
        "you",
        "he",
        "she",
        "it",
        "we",
        "they",
        "me",
        "him",
        "her",
        "us",
        "them",
        "my",
        "your",
        "his",
        "their",
        "our",
        "this",
        "that",
        "these",
        "those",
        "not",
        "no",
        "yes",
        "all",
        "any",
        "some",
        "more",
        "most",
        "other",
        "such",
        "only",
        "own",
        "same",
        "so",
        "than",
        "too",
        "very",
        "can",
        "will",
        "just",
        "should",
        "would",
        "could",
        "may",
        "might",
        "must",
        "what",
        "which",
        "who",
        "when",
        "where",
        "why",
        "how",
    }
)

# Sentence boundary regex — matches `.`, `!`, or `?` followed by space + capital.
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")
_WORD_TOKEN = re.compile(r"[a-zA-Z][a-zA-Z'-]+")
_BIGRAM_TOKEN = re.compile(r"\b[a-zA-Z]{3,}\s+[a-zA-Z]{3,}\b")


@dataclass(slots=True)
class VoiceCorpus:
    """Aggregated voice signal for a user.

    `full_text` is the concatenated corpus (newline-separated by source);
    `vocab_fingerprint` is the top-30 distinctive non-stopword tokens;
    `sentence_length_stats` holds mean / std-dev / short-medium-long pct;
    `idiomatic_phrases` is the top-10 2-word phrases by frequency.
    `voice_fingerprint_hash` is sha256:<prefix> over the full corpus +
    blocklist version (auto-invalidates Anthropic ephemeral cache).
    """

    full_text: str
    vocab_fingerprint: list[str]
    sentence_length_stats: dict[str, float]
    idiomatic_phrases: list[str]
    voice_fingerprint_hash: str
    source_counts: dict[str, int] = field(default_factory=dict)


def compute_sentence_stats(corpus_text: str) -> dict[str, float]:
    """Mean / std-dev sentence-word-count + short/medium/long pct.

    Short = ≤8 words; medium = 9-19; long = ≥20.
    """
    if not corpus_text.strip():
        return {
            "mean_words": 0.0,
            "std_dev_words": 0.0,
            "short_pct": 0.0,
            "med_pct": 0.0,
            "long_pct": 0.0,
            "sentence_count": 0.0,
        }
    sentences = [s.strip() for s in _SENTENCE_BOUNDARY.split(corpus_text) if s.strip()]
    if not sentences:
        return {
            "mean_words": 0.0,
            "std_dev_words": 0.0,
            "short_pct": 0.0,
            "med_pct": 0.0,
            "long_pct": 0.0,
            "sentence_count": 0.0,
        }
    word_counts = [len(_WORD_TOKEN.findall(s)) for s in sentences]
    total = len(word_counts)
    short = sum(1 for n in word_counts if n <= 8)
    med = sum(1 for n in word_counts if 9 <= n <= 19)
    long_ = sum(1 for n in word_counts if n >= 20)
    return {
        "mean_words": round(mean(word_counts), 2),
        "std_dev_words": round(pstdev(word_counts) if total > 1 else 0.0, 2),
        "short_pct": round(short * 100 / total, 1),
        "med_pct": round(med * 100 / total, 1),
        "long_pct": round(long_ * 100 / total, 1),
        "sentence_count": float(total),
    }


def compute_vocab_fingerprint(corpus_text: str, top_n: int = 30) -> list[str]:
    """Top-N non-stopword tokens from the corpus, lowercased."""
    if not corpus_text:
        return []
    counter: Counter[str] = Counter()
    for raw in _WORD_TOKEN.findall(corpus_text.lower()):
        if raw in _STOPWORDS or len(raw) < 3:
            continue
        counter[raw] += 1
    return [token for token, _ in counter.most_common(top_n)]


def extract_idiomatic_phrases(corpus_text: str, top_n: int = 10) -> list[str]:
    """Top-N 2-word phrases (both tokens 3+ chars, non-stopword) by count."""
    if not corpus_text:
        return []
    counter: Counter[str] = Counter()
    for match in _BIGRAM_TOKEN.findall(corpus_text.lower()):
        words = match.split()
        if len(words) != 2:
            continue
        if any(w in _STOPWORDS for w in words):
            continue
        counter[match] += 1
    return [phrase for phrase, count in counter.most_common(top_n) if count >= 2]


def voice_fingerprint_hash(full_text: str, blocklist_version: str = "v1") -> str:
    """SHA256:<32-hex-prefix> over corpus + blocklist version.

    Anthropic ephemeral prompt cache auto-invalidates when this hash
    changes (per T2). Stable across calls when the corpus is stable.
    """
    h = hashlib.sha256()
    h.update(full_text.encode("utf-8"))
    h.update(b"\n--\n")
    h.update(blocklist_version.encode("utf-8"))
    return f"sha256:{h.hexdigest()[:32]}"


async def _bullet_texts(session: AsyncSession, user_id: int) -> list[str]:
    """All non-deleted Bullet.text rows for the user (via Experience join)."""
    stmt = (
        select(Bullet.text)
        .join(Experience, Bullet.experience_id == Experience.id)
        .join(Profile, Experience.profile_id == Profile.id)
        .where(
            Profile.user_id == user_id,
            Profile.deleted_at.is_(None),
            Experience.deleted_at.is_(None),
            Bullet.deleted_at.is_(None),
        )
        .limit(200)
    )
    rows = (await session.exec(stmt)).all()
    return [str(t) for t in rows if t]


async def _profile_summaries(session: AsyncSession, user_id: int) -> list[str]:
    profile = (
        await session.exec(
            select(Profile).where(Profile.user_id == user_id, Profile.deleted_at.is_(None))
        )
    ).one_or_none()
    if profile is None:
        return []
    out: list[str] = []
    if profile.summary_full:
        out.append(profile.summary_full)
    if profile.summary_short:
        out.append(profile.summary_short)
    return out


async def _profile_answers(session: AsyncSession, user_id: int) -> list[str]:
    """Per-user reuse cache answers — STRONG voice signal (real user prose)."""
    stmt = (
        select(ProfileAnswer.answer)
        .where(ProfileAnswer.user_id == user_id)
        .order_by(ProfileAnswer.last_used_at.desc())
        .limit(100)
    )
    rows = (await session.exec(stmt)).all()
    return [str(a) for a in rows if a]


async def _settings_voice_samples(session: AsyncSession, user_id: int) -> list[str]:
    settings = (
        await session.exec(select(Settings).where(Settings.user_id == user_id))
    ).one_or_none()
    if settings is None or not settings.ai_writing_voice_samples:
        return []
    return [settings.ai_writing_voice_samples]


async def _past_trimmed_lines(session: AsyncSession, user_id: int, limit: int = 5) -> list[str]:
    """Trimmed bullet lines from the user's last N successful resumes.

    Reinforcement signal — the model can see how its prior trims fit the
    candidate's voice. Bounded by `limit` so corpus stays under token
    budget.
    """
    # GeneratedDocument has no direct user_id; join via Application.
    from models import Application

    stmt = (
        select(GeneratedDocument.bullet_selection)
        .join(Application, GeneratedDocument.application_id == Application.id)
        .where(
            Application.user_id == user_id,
            GeneratedDocument.error.is_(None),
            GeneratedDocument.bullet_selection.is_not(None),
        )
        .order_by(GeneratedDocument.compiled_at.desc())
        .limit(limit)
    )
    rows = (await session.exec(stmt)).all()
    out: list[str] = []
    for selection in rows:
        if not isinstance(selection, dict):
            continue
        trimmed = selection.get("trimmed_lines") or {}
        if not isinstance(trimmed, dict):
            continue
        out.extend(str(v) for v in trimmed.values() if v)
    return out


async def assemble_corpus(session: AsyncSession, user_id: int) -> VoiceCorpus:
    """Build the per-call voice corpus across all 5 sources.

    Returns an empty-but-valid VoiceCorpus when the user has no Profile
    yet (callers can decide to skip voice grounding for cold-start users).
    """
    bullets = await _bullet_texts(session, user_id)
    summaries = await _profile_summaries(session, user_id)
    answers = await _profile_answers(session, user_id)
    samples = await _settings_voice_samples(session, user_id)
    past_lines = await _past_trimmed_lines(session, user_id)

    sections: list[str] = []
    if bullets:
        sections.append("# Bullets\n" + "\n".join(f"- {t}" for t in bullets))
    if summaries:
        sections.append("# Profile summary\n" + "\n\n".join(summaries))
    if answers:
        sections.append("# Past screener answers\n" + "\n\n".join(answers))
    if samples:
        sections.append("# User voice samples\n" + "\n\n".join(samples))
    if past_lines:
        sections.append("# Past trimmed lines\n" + "\n".join(f"- {t}" for t in past_lines))
    full_text = "\n\n".join(sections)

    return VoiceCorpus(
        full_text=full_text,
        vocab_fingerprint=compute_vocab_fingerprint(full_text),
        sentence_length_stats=compute_sentence_stats(full_text),
        idiomatic_phrases=extract_idiomatic_phrases(full_text),
        voice_fingerprint_hash=voice_fingerprint_hash(full_text),
        source_counts={
            "bullets": len(bullets),
            "summaries": len(summaries),
            "profile_answers": len(answers),
            "voice_samples": len(samples),
            "past_trimmed_lines": len(past_lines),
        },
    )
