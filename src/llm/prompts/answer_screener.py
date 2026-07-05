"""answer_screener — Wave 6 wires this end-to-end.

Per BACKEND.md § K.4. Drafts an answer for a per-job custom screener question.
"""

from __future__ import annotations

from pydantic import BaseModel

PROMPT = """Draft an answer for this screener question on a job application.

Candidate profile:
{profile}

Job:
{job}

Question: {question}
Question type: {question_type}
{choices}

Return ScreenerAnswer with `answer` (string) and `confidence` (0.0..1.0).
For SINGLE_SELECT / MULTI_SELECT, the answer must be one of the listed
choices (or comma-separated for multi). For TEXTAREA / SHORT_TEXT, write
prose. For NUMERIC, return a number as a string.
"""


class ScreenerAnswer(BaseModel):
    answer: str
    confidence: float = 0.5
