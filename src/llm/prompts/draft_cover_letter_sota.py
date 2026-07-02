"""draft_cover_letter_sota — plan 66 (0.3.1) § T10, reworked for real
cover-letter craft.

Adaptive format dispatch:

- Scan JD for pain-point verbiage ("looking to solve" / "challenges" /
  "frustration" / etc). ≥2 matches → Pain-Letter format.
- Otherwise → Standard Hook / Match / Why-company / Close.

Voice rules (the earlier output read like a third-person bio):
- FIRST PERSON throughout — "I built…", "I'm excited about…". Never the
  candidate's name in the body, never "the candidate", never
  "<Name>'s experience is…".
- Concrete over generic: every claim traces to the candidate's actual
  bullets; verbatim phrases are listed in `verbatim_phrases`.

Replaces `draft_cover_letter.py` (T15 backward-compat — old function is
retained as a thin wrapper, marked @deprecated in its module docstring).
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from llm.base import LLMProvider

MAX_HOOK_CHARS = 400
MAX_MATCH_CHARS = 900
MAX_WHY_COMPANY_CHARS = 400
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


_VOICE_RULES = """Voice rules (non-negotiable):
- Write in the FIRST PERSON: "I built…", "I led…", "I'm excited about…".
  NEVER refer to the candidate by name or in the third person inside the
  letter body — no "{name}'s experience", no "the candidate".
- Confident and specific; zero filler ("I believe", "passionate",
  "perfect fit", "testament to"). Every claim must trace to the
  candidate's actual bullets — quote their words verbatim where natural
  and list those phrases in `verbatim_phrases`.
- Address {company} and THIS role concretely; a letter that could be sent
  to any company is a failure."""


PROMPT_STANDARD = (
    """Draft a cover letter for the candidate below applying to {company}.

Candidate:
{profile}

Job:
{job}

Hiring manager (weave naturally when present; the greeting is handled
separately):
{hiring_manager}

Match these JD keywords verbatim when they apply: {matched_tags}

"""
    + _VOICE_RULES
    + """

Structure (each section is ONE tight paragraph):
- HOOK (2-3 sentences, ≤400 chars): why me × this exact role — open with
  the single most relevant thing I've done, tied to what this team is
  building. No "I am writing to apply…" boilerplate.
- MATCH (3-5 sentences, ≤900 chars): map my 2-3 strongest, numbers-backed
  wins onto the JD's stated needs. "They need X — I did X at Y with Z
  result."
- WHY_COMPANY (2-3 sentences, ≤400 chars): why THIS company specifically —
  reference their product/mission/tech from the JD, and what I want to
  build there. Not flattery; a concrete reason.
- CLOSE (1-2 sentences, ≤300 chars): confident ask for the conversation.

Return a CoverLetterSota with format_chosen="standard".
"""
)

PROMPT_PAIN_LETTER = (
    """Draft a PAIN-LETTER format cover letter for the candidate below applying to {company}.

The JD signals the company is solving specific challenges; lead with that.

Candidate:
{profile}

Job:
{job}

Hiring manager (weave naturally when present; the greeting is handled
separately):
{hiring_manager}

Pain-point signals detected in the JD: {pain_signals}

Match these JD keywords verbatim when they apply: {matched_tags}

"""
    + _VOICE_RULES
    + """

Structure (each section is ONE tight paragraph):
- HOOK (2-3 sentences, ≤400 chars): name the pain the company described;
  show I understand it from having lived it.
- MATCH (3-5 sentences, ≤900 chars): cite my actual experience addressing
  that exact pain, with numbers.
- WHY_COMPANY (2-3 sentences, ≤400 chars): why I want to solve this at
  THIS company specifically.
- CLOSE (1-2 sentences, ≤300 chars): confident, specific ask.

Return a CoverLetterSota with format_chosen="pain_letter".
"""
)


class CoverLetterSota(BaseModel):
    """SOTA cover letter draft with adaptive format + audit trail."""

    format_chosen: Literal["standard", "pain_letter"]
    hook: str = Field(max_length=MAX_HOOK_CHARS)
    match: str = Field(max_length=MAX_MATCH_CHARS)
    why_company: str = Field(default="", max_length=MAX_WHY_COMPANY_CHARS)
    close: str = Field(max_length=MAX_CLOSE_CHARS)
    hiring_manager_used: dict[str, str | None] = Field(
        default_factory=lambda: {"name": None, "source": None}
    )
    verbatim_phrases: list[str] = Field(default_factory=list, max_length=MAX_VERBATIM_PHRASES)

    @field_validator("hook", "match", "why_company", "close", mode="before")
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

    kwargs = {
        "profile": profile_str,
        "job": job_str,
        "hiring_manager": hm_str,
        "matched_tags": ", ".join(matched_tags),
        "company": job.get("company", ""),
        "name": profile.get("full_name", ""),
    }
    if chosen == "pain_letter":
        kwargs["pain_signals"] = ", ".join(_PAIN_POINT_RE.findall(job.get("description", ""))[:5])
    rendered = prompt_template.format(**kwargs)

    result = await provider.structured(
        rendered,
        CoverLetterSota,
        max_tokens=2048,
        system=system,
        cache_system=cache_system,
    )
    return CoverLetterSota.model_validate(result.value)
