"""draft_cover_letter — DEPRECATED in favor of `draft_cover_letter_sota` (plan 66, 0.3.1).

Per BACKEND.md § K.4. 4-section letter (intro / body / why_company / close).

Kept here as a backward-compat surface (T15): existing callers still
work; the bundle endpoint (`services/bundle_generator.py`) uses
`draft_cover_letter_sota` exclusively. Slated for removal in `0.3.3`.
"""

from __future__ import annotations

from pydantic import BaseModel

PROMPT = """Draft a cover letter for this candidate × job pair.

Candidate:
{profile}

Job:
{job}

Tone: {tone}

Return CoverLetterDraft with intro, body, why_company, close. Each section
should be 2–4 sentences. Reference specific achievements from the candidate's
profile and specific details about the company / role.
"""


class CoverLetterDraft(BaseModel):
    intro: str
    body: str
    why_company: str
    close: str
