"""score_job — Wave 4 real-but-naive scoring.

Per BACKEND.md § M.3 + plan 10 Q8. Wave 4 ships the LLM call end-to-end so
the cost-tracking pipeline is exercised against real prompts. The full
scoring pipeline (visa filter, tag matching, gap analysis) is Phase 3
(plan 12). Wave 6 adds the deterministic visa filter.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from llm.base import LLMProvider

PROMPT = """You are scoring how well a candidate matches a specific job.

Candidate profile (summary + recent role):
{profile}

Job description:
Company: {company}
Role: {role}
Description:
{description}

Visa restrictions: {visa_restrictions}
Required skills: {skills}

Return a JSON object matching the JobScore schema with:
- `score`: float 0.0..1.0 — overall match
- `explanation`: 1–2 sentences on why
- `matched_tags`: tags from {{ai-ml, backend, frontend, devops, data-eng, genai, leadership, platform, product}} that align
- `gaps`: 0–3 specific gaps the candidate would need to bridge
- `visa_concern`: true if the job requires citizenship/GC and the candidate needs sponsorship
"""


class JobScore(BaseModel):
    """Structured score for a job × profile pairing."""

    score: float = Field(ge=0.0, le=1.0)
    explanation: str
    matched_tags: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    visa_concern: bool = False


async def score_job(
    provider: LLMProvider,
    *,
    profile: dict[str, Any],
    job: dict[str, Any],
) -> JobScore:
    """Score a job × profile pair via the configured LLM provider.

    Wave 4 is naive: it concats profile + JD into the prompt and trusts the
    LLM's structured output. Phase 3 will layer in deterministic tag matching
    + visa filter pre-checks.
    """
    rendered = PROMPT.format(
        profile=(
            f"{profile.get('full_name', '')}\n"
            f"{profile.get('headline', '')}\n"
            f"{profile.get('summary_short') or profile.get('summary_full', '')}"
        ),
        company=job.get("company", ""),
        role=job.get("role", ""),
        description=job.get("description", "")[:2000],
        visa_restrictions=job.get("visa_restrictions") or "none",
        skills=", ".join(job.get("skills_required", [])),
    )
    result = await provider.structured(rendered, JobScore)
    return JobScore.model_validate(result.value)
