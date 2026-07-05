"""Constitution preamble — plan 66 (0.3.1) § T3.

Structured system-message template rendered into Anthropic's cacheable
prefix (T2). Carries:

- Voice signal (sentence stats + idiomatic phrases + distinctive vocab)
- Honesty constraints (no fabrication; cite corpus)
- Style constraints (avoid AI-tells; vary length; concrete > qualitative)
- FORBIDDEN vocabulary (effective blocklist after user-vocab subtraction)
- The candidate's actual voice corpus (so the LLM has the lexicon)

The rendered string is passed to `provider.structured(..., system=..., cache_system=True)`
so Anthropic's ephemeral cache sees the same prefix across all stages of
one bundle (~12 calls in ~10s).
"""

from __future__ import annotations

from .ai_tell_blocklist import BAKED_IN_BLOCKLIST
from .voice_grounding import VoiceCorpus


def render_preamble(
    corpus: VoiceCorpus,
    profile_full_name: str,
    *,
    blocklist: set[str] | None = None,
    extra_constraints: str = "",
) -> str:
    """Render the full constitution preamble for one bundle.

    `blocklist` defaults to BAKED_IN_BLOCKLIST (use `effective_blocklist`
    upstream to get the user-vocab-aware subset). `extra_constraints`
    folds in per-stage additions (e.g. recruiter-priority instruction).
    """
    active_blocklist = blocklist if blocklist is not None else set(BAKED_IN_BLOCKLIST)
    blocklist_list = ", ".join(sorted(active_blocklist))

    stats = corpus.sentence_length_stats or {}
    short_pct = stats.get("short_pct", 0.0)
    med_pct = stats.get("med_pct", 0.0)
    long_pct = stats.get("long_pct", 0.0)
    mean_words = stats.get("mean_words", 0.0)
    std_dev = stats.get("std_dev_words", 0.0)

    idiomatic = ", ".join(corpus.idiomatic_phrases or [])
    vocab = ", ".join(corpus.vocab_fingerprint or [])

    corpus_text = corpus.full_text or "(no profile corpus available)"

    parts: list[str] = [
        f"You are tailoring application materials for {profile_full_name}.",
        "",
        "THEIR VOICE — Match this exactly when generating any output:",
        f"- Sentence-length distribution: short {short_pct}% / "
        f"medium {med_pct}% / long {long_pct}% (mean {mean_words} words, "
        f"std-dev {std_dev})",
    ]
    if idiomatic:
        parts.append(f"- Idiomatic phrases they use: {idiomatic}")
    if vocab:
        parts.append(f"- Distinctive vocabulary (top tokens): {vocab}")

    parts += [
        "",
        "THEIR EXPERIENCE (corpus follows; everything below is the candidate's own writing):",
        corpus_text,
        "",
        "HONESTY CONSTRAINTS:",
        "- NEVER claim experience not grounded in the corpus above.",
        "- NEVER inflate titles or fabricate credentials.",
        "- Every bullet you emit must trace to a corpus bullet. If you "
        "cannot point to a corpus source, drop the bullet.",
        "",
        "STYLE CONSTRAINTS:",
        "- Avoid AI-tell vocabulary (see FORBIDDEN list below).",
        "- Vary sentence length deliberately. Mix short (≤8 words) and "
        "long (≥20 words) sentences across the same output.",
        "- Prefer specific verbs over generic. Prefer concrete numbers over qualitative claims.",
        "- Do NOT use em-dashes (—). Use commas or periods.",
        "",
        f"FORBIDDEN VOCABULARY (case-insensitive; do not use): {blocklist_list}",
    ]

    if extra_constraints:
        parts += ["", extra_constraints.strip()]

    return "\n".join(parts).strip()
