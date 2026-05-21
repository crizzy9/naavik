"""council_personas — plan 67 (0.3.4) § C.2.

Three heterogeneous personas for bullet-selection voting council. Each
returns a full ordering of the candidate bullet set; Borda count merges
the rankings into a final selection.

Personas (per research § G.3):
- pragmatic_recruiter — 6-second skim + ATS keyword coverage bias
- hiring_manager      — senior-level impact + scope + tech-stack signal
- cultural_fit        — collaboration + impact + growth signal
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

PERSONAS: tuple[str, ...] = ("pragmatic_recruiter", "hiring_manager", "cultural_fit")

PRAGMATIC_RECRUITER_PROMPT = """You are a PRAGMATIC RECRUITER at the
hiring company. Time-pressed, 6-second skim, ATS parsing in mind.

Pick the bullets that read as strongest matches to the JD's required
skills. Prioritize:
- Verbatim keyword coverage (the bullet uses the JD's actual words)
- Quantification (numbers + scale + outcomes)
- Clean parse (no jargon-heavy run-ons that ATS will mangle)

Candidate bullets (id -> text):
{bullets}

Job:
Role: {role}
Description (first 1500 chars): {description}
Required skills: {skills}

Rank ALL candidate bullets best (most likely to land) to worst. Output
must be a CouncilVote with persona="pragmatic_recruiter",
ranked_bullet_ids containing EVERY input id exactly once, and a
1-sentence rationale.
"""

HIRING_MANAGER_PROMPT = """You are a HIRING MANAGER who will work
directly with the new hire. You read deeper than the recruiter and
care about technical depth.

Pick bullets that signal:
- Senior-level scope (autonomous decisions, multi-team impact)
- Specific tech-stack overlap with what your team uses
- Ownership stories (the candidate drove vs participated)
- Recent ship velocity (not just years of titles)

Candidate bullets (id -> text):
{bullets}

Job:
Role: {role}
Description (first 1500 chars): {description}
Required skills: {skills}

Rank ALL candidate bullets best (signals strongest senior fit) to worst.
Output must be a CouncilVote with persona="hiring_manager",
ranked_bullet_ids containing EVERY input id exactly once, and a
1-sentence rationale.
"""

CULTURAL_FIT_PROMPT = """You are a CULTURAL-FIT ASSESSOR (think
people-team round at a culture-driven company). You read for shape:
how the candidate works, not just what they shipped.

Pick bullets that signal:
- Collaboration (worked with, partnered with, paired with)
- Growth + curiosity (learned, taught, mentored)
- Impact in scale (cross-functional, org-wide, customer-facing)
- Voice (sounds like a real person, not a SaaS feature page)

Candidate bullets (id -> text):
{bullets}

Job:
Role: {role}
Company: {company}
Description (first 1500 chars): {description}

Rank ALL candidate bullets best (strongest cultural fit) to worst.
Output must be a CouncilVote with persona="cultural_fit",
ranked_bullet_ids containing EVERY input id exactly once, and a
1-sentence rationale.
"""


class CouncilVote(BaseModel):
    """One persona's ordered ranking of candidate bullets."""

    persona: Literal["pragmatic_recruiter", "hiring_manager", "cultural_fit"]
    ranked_bullet_ids: list[int] = Field(default_factory=list)
    rationale: str = Field(default="", max_length=400)


def _format_bullets(candidates: list[dict]) -> str:
    return "\n".join(f"{b['id']} -> {b['text']}" for b in candidates)


def build_pragmatic_recruiter_prompt(candidates: list[dict], job: dict) -> str:
    return PRAGMATIC_RECRUITER_PROMPT.format(
        bullets=_format_bullets(candidates),
        role=job.get("role", ""),
        description=(job.get("description") or "")[:1500],
        skills=", ".join(job.get("skills_required") or []),
    )


def build_hiring_manager_prompt(candidates: list[dict], job: dict) -> str:
    return HIRING_MANAGER_PROMPT.format(
        bullets=_format_bullets(candidates),
        role=job.get("role", ""),
        description=(job.get("description") or "")[:1500],
        skills=", ".join(job.get("skills_required") or []),
    )


def build_cultural_fit_prompt(candidates: list[dict], job: dict) -> str:
    return CULTURAL_FIT_PROMPT.format(
        bullets=_format_bullets(candidates),
        role=job.get("role", ""),
        company=job.get("company", ""),
        description=(job.get("description") or "")[:1500],
    )


PROMPT_BUILDERS = {
    "pragmatic_recruiter": build_pragmatic_recruiter_prompt,
    "hiring_manager": build_hiring_manager_prompt,
    "cultural_fit": build_cultural_fit_prompt,
}
