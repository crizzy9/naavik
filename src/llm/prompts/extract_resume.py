"""extract_resume — Wave 6 wires this end-to-end (Onboarding step 2).

Per BACKEND.md § M.3. Wave 4 ships the schema skeleton.
"""

from __future__ import annotations

from pydantic import BaseModel

from llm.base import LLMProvider

PROMPT = """Extract a candidate profile from this resume PDF text.

Resume text:
{resume_text}

Return ExtractedResume with full_name, headline, summary, experiences[],
skills[], educations[], projects[]. Each experience has bullets[] (long-form
text, one per achievement), tags[] (from the 9-tag vocabulary).
"""


class ExtractedExperience(BaseModel):
    company: str
    title: str
    team: str | None = None
    location: str | None = None
    start_date: str | None = None  # ISO date string
    end_date: str | None = None
    bullets: list[str] = []
    bullet_tags: list[list[str]] = []  # parallel to bullets


class ExtractedResume(BaseModel):
    full_name: str
    headline: str | None = None
    location: str | None = None
    email: str | None = None
    phone: str | None = None
    summary_full: str | None = None
    summary_short: str | None = None
    experiences: list[ExtractedExperience] = []
    skills: list[dict] = []  # [{category, items[]}]
    educations: list[dict] = []
    projects: list[dict] = []


async def extract_resume(
    provider: LLMProvider,
    *,
    resume_text: str,
) -> ExtractedResume:
    rendered = PROMPT.format(resume_text=resume_text[:30_000])
    result = await provider.structured(rendered, ExtractedResume, max_tokens=4096)
    return ExtractedResume.model_validate(result.value)
