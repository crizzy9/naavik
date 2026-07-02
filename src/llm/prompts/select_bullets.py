"""select_bullets — rank the FULL bullet inventory against a JD.

The document generator no longer asks for a top-N cut: it wants every
candidate bullet in priority order, then packs the page as densely as it
will go (dropping from the tail on Typst overflow, never emptying an
experience). `selected_ids` therefore carries a full ranking.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from llm.base import LLMProvider

PROMPT = """Rank ALL of the candidate's resume bullets by relevance to this job,
most relevant first.

Profile bullets (id → text):
{bullets}

Job:
Role: {role}
Description: {description}
Required skills: {skills}

Ranking guidance:
- Bullets that hit the JD's core responsibilities and named technologies rank
  highest; generic bullets rank lowest.
- Prefer bullets with concrete numbers/results over vague ones at equal
  relevance.
- Return EVERY id exactly once in `selected_ids`, ordered by priority. Do not
  invent ids and do not omit any.

Return BulletSelection with the complete ranking in selected_ids.
"""


class BulletSelection(BaseModel):
    selected_ids: list[int] = Field(default_factory=list)
    rationale: str = ""


async def select_bullets(
    provider: LLMProvider,
    *,
    bullets: list[dict],
    job: dict,
) -> BulletSelection:
    bullets_text = "\n".join(f"{b['id']} → {b['text']}" for b in bullets)
    rendered = PROMPT.format(
        bullets=bullets_text,
        role=job.get("role", ""),
        description=job.get("description", "")[:1500],
        skills=", ".join(job.get("skills_required", [])),
    )
    result = await provider.structured(rendered, BulletSelection, max_tokens=1024)
    return BulletSelection.model_validate(result.value)
