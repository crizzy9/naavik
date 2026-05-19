"""extract_job — Phase 2 wires this end-to-end (scraper pipeline).

Per BACKEND.md § J.3, § M.3. Wave 4 ships the schema skeleton. Plan 27
(0.2.0.05) replaces `visa_restrictions: str` with typed `VisaRestriction`
enum so AI extraction output is structurally constrained.
"""

from __future__ import annotations

from pydantic import BaseModel

from llm.base import LLMProvider
from models.enums import VisaRestriction

PROMPT = """Extract a structured job listing from this scraped HTML.

HTML:
{html}

Return ExtractedJob with company, role, team, location, description (plain
text), criteria[], skills_required[], visa_restrictions, salary_min, salary_max,
equity_pct, posted_at (ISO date).

For visa_restrictions, choose ONE of:
- "us_citizen_only" — JD requires US citizenship
- "green_card_required" — JD requires green card / permanent residency
- "sponsorship_available" — JD explicitly offers H1B / visa sponsorship
- "not_mentioned" — JD does not say (default)
"""


class ExtractedJob(BaseModel):
    company: str
    role: str
    team: str | None = None
    location: str | None = None
    description: str
    criteria: list[str] = []
    skills_required: list[str] = []
    visa_restrictions: VisaRestriction = VisaRestriction.NOT_MENTIONED
    salary_min: int | None = None
    salary_max: int | None = None
    equity_pct: float | None = None
    posted_at: str | None = None


async def extract_job(provider: LLMProvider, *, html: str) -> ExtractedJob:
    rendered = PROMPT.format(html=html[:30_000])
    result = await provider.structured(rendered, ExtractedJob, max_tokens=2048)
    return ExtractedJob.model_validate(result.value)
