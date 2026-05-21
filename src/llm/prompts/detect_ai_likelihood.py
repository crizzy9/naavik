"""detect_ai_likelihood — plan 67 (0.3.4) § C.1.

Claude-as-detector inner-loop prompt. Asks the model to score the supplied
text on AI-likelihood (0.0 - 1.0) AND identify the specific phrases that
read most like AI-generated content. Phrase-level signal feeds the
refine_to_human pass.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

PROMPT = """You are an expert AI-text detector (think GPTZero, Originality.ai).

Read the text below. Score how likely it is that an LLM wrote it.

Scoring guide:
- 0.0 - 0.2  Clearly human; idiosyncratic, irregular, specific.
- 0.2 - 0.5  Probably human, with some smooth phrases.
- 0.5 - 0.8  Mixed; smells AI-edited or LLM-drafted then revised.
- 0.8 - 1.0  Reads as AI; uniform sentence rhythm, hedging vocabulary,
             em-dashes, transition words ("furthermore", "delve",
             "leverage", "robust", "comprehensive").

Identify up to 5 specific phrases (≤12 words each) that read most like
AI. These will be rewritten by hand. Pick concrete phrases (not whole
sentences) and include enough context to find them.

Text to score:
{text}

Return a DetectorVerdict with `ai_confidence`, `flagged_phrases`, and a
1-sentence `rationale` explaining the score.
"""


class DetectorVerdict(BaseModel):
    """Claude-as-detector output for one iteration."""

    ai_confidence: float = Field(ge=0.0, le=1.0)
    flagged_phrases: list[str] = Field(default_factory=list, max_length=5)
    rationale: str = Field(default="", max_length=400)


def build_prompt(text: str) -> str:
    """Format the Claude-as-detector user message for `text`."""
    return PROMPT.format(text=text[:8000])
