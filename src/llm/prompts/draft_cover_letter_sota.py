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
- This letter is FROM the candidate, in THEIR words. Write in the first
  person, the way they actually write — their corpus is in the system
  context and their verbatim writing samples are in the Candidate block
  below. Reuse THEIR nouns, verbs, and phrasing; do not translate their
  work into cover-letter vocabulary.
- Plain, spoken register. Contractions are fine. Short sentences are fine.
  The letter should read like a sharp, direct note from a real engineer —
  not a formal letter someone ghost-wrote FOR them.
- NEVER refer to the candidate by name or in the third person inside the
  letter body — no "{name}'s experience", no "the candidate".
- BANNED — generic cover-letter register (and anything in its family):
  "I am writing to apply", "I'd welcome the chance/opportunity",
  "excited to apply", "proven track record", "passionate", "perfect fit",
  "leverage", "aligns with", "resonates", "I believe", "testament to",
  "ready to go deeper", "hit the ground running", "make an impact".
  If a sentence could appear in anyone's letter, cut it.
- Any internal category tags provided (e.g. "backend", "ai-ml") are for
  orientation ONLY — NEVER print them in the letter.
- Every claim must trace to the candidate's actual bullets — quote their
  words verbatim where natural and list those phrases in `verbatim_phrases`.
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

Overlap themes (INTERNAL tags — orientation only, never print them):
{matched_tags}

"""
    + _VOICE_RULES
    + """

Structure (each section is ONE tight paragraph; the labels are internal —
never write "hook" or headers into the letter):
- HOOK (2-3 sentences, ≤400 chars): open with the single most relevant
  thing the candidate has actually done, tied to what this team is
  building — stated the way THEY would state it.
- MATCH (3-5 sentences, ≤900 chars): connect their 2-3 strongest,
  numbers-backed wins to what the JD actually asks for. No formula — write
  it the way they'd explain their own work to another engineer, keeping
  their original phrasing wherever it fits.
- WHY_COMPANY (2-3 sentences, ≤400 chars): one concrete reason THIS
  company/product/tech is interesting to them, grounded in the JD. Plain
  words; no flattery, no mission-statement echo.
- CLOSE (1-2 sentences, ≤300 chars): ask for the conversation like a
  person, not a salesman.

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

Overlap themes (INTERNAL tags — orientation only, never print them):
{matched_tags}

"""
    + _VOICE_RULES
    + """

Structure (each section is ONE tight paragraph; the labels are internal —
never write "hook" or headers into the letter):
- HOOK (2-3 sentences, ≤400 chars): name the pain the company described;
  show the candidate understands it from having lived it — in their words.
- MATCH (3-5 sentences, ≤900 chars): cite their actual experience
  addressing that exact pain, with numbers, keeping their original
  phrasing wherever it fits.
- WHY_COMPANY (2-3 sentences, ≤400 chars): why solving this at THIS
  company specifically is interesting to them. Plain words.
- CLOSE (1-2 sentences, ≤300 chars): a plain, specific ask.

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
