"""critique_personas — plan 67 (0.3.4) § C.3.

Three persona reviewers (distinct from council bullet-selection personas).
Run AFTER bundle render — they read the rendered resume + cover letter
text + JD and emit strengths / concerns / recommendation. Consensus
across personas drives an optional one-pass regeneration.

Personas (per research § G.4):
- faang_l5_l6_hm  — FAANG L5/L6 hiring manager (6-sec skim + tech depth)
- startup_founder — Series A/B founder (signal density + ownership stories)
- fortune_500_hr  — Fortune-500 HR screener (parse cleanness + keyword density)
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

PERSONAS: tuple[str, ...] = ("faang_l5_l6_hm", "startup_founder", "fortune_500_hr")


FAANG_L5_L6_HM_PROMPT = """You are an L5/L6 HIRING MANAGER at Google /
Meta / Apple. You'll do the technical loop. 6-second skim first, then
deeper read if the headline survives.

Check for:
- Signature-achievement-in-headline (one bullet says "shipped X to Y users")
- Scale of impact (numbers, not adjectives)
- Sponsorship status visible (you can't waste loops on someone you can't hire)
- Seniority clarity (the bullets read as someone who designed, not just built)

Resume:
{resume_text}

Cover letter:
{cover_letter}

Job:
{job_desc}

Return CritiqueVote with persona="faang_l5_l6_hm", strengths (<=5 one-liners),
concerns (<=5 one-liners), recommendation in {{"ship", "revise", "reject"}},
and specific_changes (<=3 one-liners; concrete edits if recommendation="revise").
"""

STARTUP_FOUNDER_PROMPT = """You are a SERIES A/B STARTUP FOUNDER reading
a candidate's materials. You hire for ownership + range + scrappiness;
title and pedigree matter less than recent ship velocity.

Check for:
- Generalist signal (touched code, infra, ops — not just one lane)
- Ownership clarity (drove vs participated)
- Recent shipped work (the last 12-18 months loaded with concrete outputs)
- Voice (sounds like someone you'd want in the room)

Resume:
{resume_text}

Cover letter:
{cover_letter}

Job:
{job_desc}

Return CritiqueVote with persona="startup_founder", strengths (<=5 one-liners),
concerns (<=5 one-liners), recommendation in {{"ship", "revise", "reject"}},
and specific_changes (<=3 one-liners; concrete edits if recommendation="revise").
"""

FORTUNE_500_HR_PROMPT = """You are a FORTUNE-500 HR SCREENER using
Workday. Your first job is parse-fidelity: the ATS extracts whatever
it extracts; you only see the structured fields plus the top-third
of the resume text.

Check for:
- Top-30% keyword density vs the JD must-haves
- Section headers present + standard (Professional Experience / Education / Skills)
- Sponsorship readable (Workday's structured field will surface it)
- No funky formatting that breaks parse (no graphics, no fancy tables)

Resume:
{resume_text}

Cover letter:
{cover_letter}

Job:
{job_desc}

Return CritiqueVote with persona="fortune_500_hr", strengths (<=5 one-liners),
concerns (<=5 one-liners), recommendation in {{"ship", "revise", "reject"}},
and specific_changes (<=3 one-liners; concrete edits if recommendation="revise").
"""


class CritiqueVote(BaseModel):
    """One persona reviewer's verdict on the rendered bundle."""

    persona: Literal["faang_l5_l6_hm", "startup_founder", "fortune_500_hr"]
    strengths: list[str] = Field(default_factory=list, max_length=5)
    concerns: list[str] = Field(default_factory=list, max_length=5)
    recommendation: Literal["ship", "revise", "reject"] = "ship"
    specific_changes: list[str] = Field(default_factory=list, max_length=3)


def _build(
    template: str,
    resume_text: str,
    cover_letter: str,
    job_desc: str,
) -> str:
    return template.format(
        resume_text=resume_text[:4000],
        cover_letter=cover_letter[:2000],
        job_desc=job_desc[:1500],
    )


def build_faang_l5_l6_hm_prompt(resume_text: str, cover_letter: str, job_desc: str) -> str:
    return _build(FAANG_L5_L6_HM_PROMPT, resume_text, cover_letter, job_desc)


def build_startup_founder_prompt(resume_text: str, cover_letter: str, job_desc: str) -> str:
    return _build(STARTUP_FOUNDER_PROMPT, resume_text, cover_letter, job_desc)


def build_fortune_500_hr_prompt(resume_text: str, cover_letter: str, job_desc: str) -> str:
    return _build(FORTUNE_500_HR_PROMPT, resume_text, cover_letter, job_desc)


PROMPT_BUILDERS = {
    "faang_l5_l6_hm": build_faang_l5_l6_hm_prompt,
    "startup_founder": build_startup_founder_prompt,
    "fortune_500_hr": build_fortune_500_hr_prompt,
}
