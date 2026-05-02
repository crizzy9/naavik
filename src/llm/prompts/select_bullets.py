"""select_bullets — Wave 6 wires this end-to-end (resume tailoring).

Per BACKEND.md § K.4, § M.3.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from llm.base import LLMProvider

PROMPT = """Select the {max} most relevant bullets for this job.

Profile bullets (id → text):
{bullets}

Job:
Role: {role}
Description: {description}
Required skills: {skills}

Honor `selection_override` rules (always_include must appear; never_include
must NOT appear). Return BulletSelection with selected_ids in order of
priority for the resume.
"""


class BulletSelection(BaseModel):
    selected_ids: list[int] = Field(default_factory=list)
    rationale: str = ""


async def select_bullets(
    provider: LLMProvider,
    *,
    bullets: list[dict],
    job: dict,
    max_select: int = 12,
) -> BulletSelection:
    bullets_text = "\n".join(f"{b['id']} → {b['text']}" for b in bullets)
    rendered = PROMPT.format(
        max=max_select,
        bullets=bullets_text,
        role=job.get("role", ""),
        description=job.get("description", "")[:1000],
        skills=", ".join(job.get("skills_required", [])),
    )
    result = await provider.structured(rendered, BulletSelection, max_tokens=1024)
    return BulletSelection.model_validate(result.value)
