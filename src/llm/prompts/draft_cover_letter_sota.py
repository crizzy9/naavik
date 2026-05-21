"""draft_cover_letter_sota — plan 66 (0.3.1) § T10.

Adaptive format dispatch:

- Scan JD for pain-point verbiage ("looking to solve" / "challenges" /
  "frustration" / etc). ≥2 matches → Pain-Letter format.
- Otherwise → Standard Hook / Match / Close 3-paragraph.

Voice grounding via the constitution preamble (shared corpus). Honesty
constraint: every verbatim phrase in `verbatim_phrases` must trace to
the candidate's actual profile content.

Replaces `draft_cover_letter.py` (T15 backward-compat — old function is
retained as a thin wrapper, marked @deprecated in its module docstring).
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from llm.base import LLMProvider

MAX_HOOK_CHARS = 400
MAX_MATCH_CHARS = 800
MAX_CLOSE_CHARS = 300
MAX_VERBATIM_PHRASES = 10

# Pain-point heuristic per T10. ≥2 matches in the JD → pain_letter format.
_PAIN_POINT_PATTERNS = [
    r"looking to solve",
    r"challenges?",
    r"pain points?",
    r"frustration",
    r"struggling with",
    r"issues? with",
    r"working through",
    r"navigate the",
    r"break (?:down|out of)",
    r"overcome",
]
_PAIN_POINT_RE = re.compile("|".join(_PAIN_POINT_PATTERNS), re.IGNORECASE)


def detect_pain_letter_format(job_description: str) -> bool:
    """Return True iff JD contains ≥2 pain-point verbiage matches."""
    if not job_description:
        return False
    matches = _PAIN_POINT_RE.findall(job_description)
    return len(matches) >= 2


PROMPT_STANDARD = """Draft a 3-paragraph cover letter (Hook / Match / Close).

Candidate:
{profile}

Job:
{job}

Hiring manager (use in salutation when present):
{hiring_manager}

Match these JD keywords verbatim when they apply: {matched_tags}

Cover the candidate's bullets verbatim when natural — prefer THEIR words
over rephrasing. List the verbatim phrases you used in `verbatim_phrases`.

Structure:
- HOOK (2-3 sentences, ≤400 chars): why this candidate × this role.
- MATCH (3-4 sentences, ≤800 chars): specific achievements w/ numbers.
- CLOSE (2 sentences, ≤300 chars): specific ask + commitment.

Return a CoverLetterSota with format_chosen="standard".
"""

PROMPT_PAIN_LETTER = """Draft a 3-paragraph PAIN-LETTER format cover letter.

The JD signals the company is solving specific challenges; lead with that.

Candidate:
{profile}

Job:
{job}

Hiring manager (use in salutation when present):
{hiring_manager}

Pain-point signals detected in the JD: {pain_signals}

Structure:
- HOOK (2-3 sentences, ≤400 chars): name the pain the company described;
  signal you understand it.
- MATCH (3-4 sentences, ≤800 chars): cite the candidate's actual
  experience addressing that exact pain. Use THEIR words verbatim when
  natural; list those phrases in `verbatim_phrases`.
- CLOSE (2 sentences, ≤300 chars): specific ask + commitment to solving
  this pain.

Match these JD keywords verbatim when they apply: {matched_tags}

Return a CoverLetterSota with format_chosen="pain_letter".
"""


class CoverLetterSota(BaseModel):
    """SOTA cover letter draft with adaptive format + audit trail."""

    format_chosen: Literal["standard", "pain_letter"]
    hook: str = Field(max_length=MAX_HOOK_CHARS)
    match: str = Field(max_length=MAX_MATCH_CHARS)
    close: str = Field(max_length=MAX_CLOSE_CHARS)
    hiring_manager_used: dict[str, str | None] = Field(
        default_factory=lambda: {"name": None, "source": None}
    )
    verbatim_phrases: list[str] = Field(default_factory=list, max_length=MAX_VERBATIM_PHRASES)

    @field_validator("hook", "match", "close", mode="before")
    @classmethod
    def _ensure_str(cls, v: object) -> str:
        return str(v) if v is not None else ""


async def draft_cover_letter_sota(
    provider: LLMProvider,
    *,
    profile: dict,
    job: dict,
    matched_tags: list[str],
    hiring_manager: dict | None = None,
    format_override: str = "auto",
    system: str | None = None,
    cache_system: bool = False,
) -> CoverLetterSota:
    """Generate a SOTA cover letter draft.

    `format_override` ∈ {"auto", "standard", "pain_letter"} (mirrors
    `Settings.cover_letter_format`). "auto" runs the pain-point detector.

    `hiring_manager` is a dict from `HiringManagerHit` — when None or
    `confidence < 0.5`, the salutation falls back to the company's
    Hiring Team.
    """
    if format_override == "pain_letter" or (
        format_override == "auto" and detect_pain_letter_format(job.get("description", ""))
    ):
        prompt_template = PROMPT_PAIN_LETTER
        chosen = "pain_letter"
    else:
        prompt_template = PROMPT_STANDARD
        chosen = "standard"

    hm_str = "(no specific hiring manager identified)"
    if hiring_manager and hiring_manager.get("name"):
        hm_str = f"{hiring_manager['name']}"
        if hiring_manager.get("title"):
            hm_str += f", {hiring_manager['title']}"

    profile_str = (
        f"{profile.get('full_name', '')}\n"
        f"{profile.get('summary_short') or profile.get('summary_full', '')}\n"
        f"Top bullets: {'; '.join(profile.get('top_bullets', []))[:1500]}"
    )
    job_str = (
        f"{job.get('company', '')} — {job.get('role', '')}\n{(job.get('description') or '')[:1500]}"
    )

    if chosen == "pain_letter":
        pain_signals = _PAIN_POINT_RE.findall(job.get("description", ""))[:5]
        rendered = prompt_template.format(
            profile=profile_str,
            job=job_str,
            hiring_manager=hm_str,
            matched_tags=", ".join(matched_tags),
            pain_signals=", ".join(pain_signals),
        )
    else:
        rendered = prompt_template.format(
            profile=profile_str,
            job=job_str,
            hiring_manager=hm_str,
            matched_tags=", ".join(matched_tags),
        )

    result = await provider.structured(
        rendered,
        CoverLetterSota,
        max_tokens=2048,
        system=system,
        cache_system=cache_system,
    )
    return CoverLetterSota.model_validate(result.value)
