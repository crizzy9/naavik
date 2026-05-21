"""refine_to_human — plan 67 (0.3.4) § C.1.

Phrase-targeted refine pass. Given the original text + a set of
flagged phrases that read as AI, asks Claude to rewrite ONLY those
phrases to sound more like the candidate's actual writing. Preserves
voice grounding from the constitution preamble passed in `system`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

PROMPT = """The text below was flagged as reading too AI-like. Rewrite
ONLY the specific flagged phrases to sound more like a real engineer's
voice. Keep every number, every verb, every specific claim.

Do NOT rewrite the whole text. Only the flagged phrases get rewritten.
The rest of the text stays verbatim. Use the candidate's actual voice
from the system message — short sentences mixed with long, concrete
numbers over hedging, no em-dashes, no AI-tell vocabulary.

Original text:
{text}

Phrases to rewrite (rewrite each in-place):
{flagged_phrases}

Return a RefinedText with:
- `rewritten` — the full text with ONLY the flagged phrases replaced.
- `changes` — list of `"before -> after"` strings, one per replaced phrase.
"""


class RefinedText(BaseModel):
    """Refine-pass output. `rewritten` is the full text after edits."""

    rewritten: str = Field(default="")
    changes: list[str] = Field(default_factory=list, max_length=10)


def build_prompt(text: str, flagged_phrases: list[str]) -> str:
    """Format the refine-to-human user message."""
    bullet_phrases = "\n".join(f"- {p}" for p in flagged_phrases) if flagged_phrases else "(none)"
    return PROMPT.format(text=text[:8000], flagged_phrases=bullet_phrases)
