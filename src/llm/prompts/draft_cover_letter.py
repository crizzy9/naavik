"""draft_cover_letter — Wave 6 wires this end-to-end.

Per BACKEND.md § K.4. 4-section letter (intro / body / why_company / close).
"""

from __future__ import annotations

from pydantic import BaseModel

from llm.base import LLMProvider

PROMPT = """Draft a cover letter for this candidate × job pair.

Candidate:
{profile}

Job:
{job}

Tone: {tone}

Return CoverLetterDraft with intro, body, why_company, close. Each section
should be 2–4 sentences. Reference specific achievements from the candidate's
profile and specific details about the company / role.
"""


class CoverLetterDraft(BaseModel):
    intro: str
    body: str
    why_company: str
    close: str


async def draft_cover_letter(
    provider: LLMProvider,
    *,
    profile: dict,
    job: dict,
    tone: str = "enthusiastic",
) -> CoverLetterDraft:
    rendered = PROMPT.format(
        profile=f"{profile.get('full_name')}\n{profile.get('summary_short') or profile.get('summary_full', '')}",
        job=f"{job.get('company')} — {job.get('role')}\n{job.get('description', '')[:1500]}",
        tone=tone,
    )
    result = await provider.structured(rendered, CoverLetterDraft, max_tokens=2048)
    return CoverLetterDraft.model_validate(result.value)
