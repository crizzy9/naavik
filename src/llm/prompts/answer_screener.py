"""answer_screener — Wave 6 wires this end-to-end.

Per BACKEND.md § K.4. Drafts an answer for a per-job custom screener question.
"""

from __future__ import annotations

from pydantic import BaseModel

from llm.base import LLMProvider

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


async def answer_screener(
    provider: LLMProvider,
    *,
    profile: dict,
    job: dict,
    question_text: str,
    question_type: str = "TEXTAREA",
    choices: list[str] | None = None,
) -> ScreenerAnswer:
    choices_str = f"Choices: {choices}" if choices else ""
    rendered = PROMPT.format(
        profile=f"{profile.get('full_name')}\n{profile.get('summary_short') or ''}",
        job=f"{job.get('company')} — {job.get('role')}",
        question=question_text,
        question_type=question_type,
        choices=choices_str,
    )
    result = await provider.structured(rendered, ScreenerAnswer, max_tokens=512)
    return ScreenerAnswer.model_validate(result.value)
