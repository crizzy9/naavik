"""AI-tell vocabulary blocklist — plan 66 (0.3.1) § T4.

30 curated baked-in entries + dynamic subtractions from the user's own
voice corpus (so we don't strip words the user naturally uses) + em-dash
regex replacement. Two-layer enforcement:

1. Prompt-level — full list rendered into constitution preamble FORBIDDEN.
2. Post-process strip — regex sweep over LLM output; violations recorded.

Em-dash (` — `) is the single most common AI tell. We replace it with
either ", " (mid-sentence) or ". " (sentence-boundary) based on context.
"""

from __future__ import annotations

import re

# 30 baked-in entries. Order is intentional — em-dash first because it's
# the most common AI tell.
BAKED_IN_BLOCKLIST: frozenset[str] = frozenset(
    {
        "delve",
        "delving",
        "leverage",
        "leveraging",
        "leveraged",
        "robust",
        "robustly",
        "moreover",
        "furthermore",
        "in conclusion",
        "underscore",
        "underscores",
        "harness",
        "harnessing",
        "pivotal",
        "paramount",
        "intricate",
        "nuanced",
        "multifaceted",
        "holistic",
        "synergy",
        "synergistic",
        "deeply",
        "comprehensive",
        "extensive",
        "substantial",
        "significantly",
        "particularly",
        "ultimately",
        "tapestry",
    }
)

BLOCKLIST_VERSION = "v1"

# Em-dash characters: figure (U+2012), en-dash (U+2013), em-dash (U+2014),
# horizontal-bar (U+2015). Treat all as the same AI tell.
_EM_DASH_RE = re.compile(r"\s*[‒–—―]\s*")
# Sentence-boundary heuristic: em-dash followed by capital letter → ". "
_SENTENCE_BOUNDARY_EM_DASH_RE = re.compile(r"\s*[‒–—―]\s*(?=[A-Z])")


def effective_blocklist(voice_corpus_text: str | None = None) -> set[str]:
    """Return blocklist minus entries the user naturally uses.

    Scans the corpus for case-insensitive whole-word occurrences. If a
    baked-in entry appears in the corpus, it's removed from the active
    list (the user uses this word; don't strip it from their tailored
    output).
    """
    if not voice_corpus_text:
        return set(BAKED_IN_BLOCKLIST)
    active = set(BAKED_IN_BLOCKLIST)
    lower_corpus = voice_corpus_text.lower()
    for term in BAKED_IN_BLOCKLIST:
        # Whole-word match (\b...\b). Multi-word terms still work because
        # the regex anchors on the entire substring.
        pattern = r"\b" + re.escape(term) + r"\b"
        if re.search(pattern, lower_corpus):
            active.discard(term)
    return active


def _replace_em_dashes(text: str) -> str:
    """Replace em-dash family with `, ` (mid-sentence) or `. ` (boundary).

    Order matters: the sentence-boundary regex runs first so it picks up
    cases like `foo — Bar` (replace with `. Bar`); the remaining em-dashes
    fall through to `, `.
    """
    text = _SENTENCE_BOUNDARY_EM_DASH_RE.sub(". ", text)
    text = _EM_DASH_RE.sub(", ", text)
    return text


def strip_violations(text: str, blocklist: set[str] | None = None) -> tuple[str, list[str]]:
    """Scrub blocklisted vocab + em-dashes from `text`.

    Returns `(scrubbed_text, list_of_violations)`. The violation list
    carries the actual blocklisted terms found (case-preserving from
    the original text) so the audit trail captures which AI-tells the
    LLM emitted before the strip.

    Em-dash replacement always runs (independent of `blocklist`). If
    em-dashes were found, the literal string `"em-dash"` appears in the
    violation list.
    """
    if blocklist is None:
        blocklist = set(BAKED_IN_BLOCKLIST)
    violations: list[str] = []

    if _EM_DASH_RE.search(text):
        violations.append("em-dash")
    scrubbed = _replace_em_dashes(text)

    for term in blocklist:
        pattern = re.compile(r"\b" + re.escape(term) + r"\b", re.IGNORECASE)
        if pattern.search(scrubbed):
            violations.append(term)
            # Replace with empty + clean up double spaces. Caller may want to
            # pass the scrubbed text back to the LLM with the violation
            # noted; we don't word-substitute here to avoid grammar bugs.
            scrubbed = pattern.sub("", scrubbed)
            scrubbed = re.sub(r"\s{2,}", " ", scrubbed).strip()

    return scrubbed, violations
