"""tailor_summary — JD-tailored resume summary.

The summary at the top of the tailored resume is rewritten per job: a tight
2–3 line pitch that leads with the candidate's strongest overlap with the
JD instead of the generic profile boilerplate.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

MAX_SUMMARY_CHARS = 380

PROMPT = """Write the SUMMARY section for the top of {name}'s resume, tailored
to the job below.

Candidate profile:
{profile}

Their strongest bullets (source of truth — never claim anything not here):
{bullets}

Job:
{job}

Rules:
- 2–3 sentences, at most {max_chars} characters total.
- Resume convention: no "I" — start with a role identity that mirrors the
  job title (e.g. "Senior software engineer with 6+ years ...").
- Lead with the single strongest overlap between the candidate's record and
  the JD's core need; name 2–3 concrete technologies or domains that appear
  in BOTH the JD and the candidate's record.
- Close with one concrete, numbers-backed differentiator taken from the
  bullets.
- No filler ("passionate", "results-driven", "proven track record"), no
  fabrication, no skills the candidate doesn't have.

Return TailoredSummary with the summary text.
"""


class TailoredSummary(BaseModel):
    summary: str = Field(max_length=MAX_SUMMARY_CHARS + 120)  # slack for validator trim

    @field_validator("summary", mode="before")
    @classmethod
    def _clean(cls, v: object) -> str:
        s = str(v or "").strip()
        return s[: MAX_SUMMARY_CHARS + 120]


def render_prompt(*, name: str, profile_text: str, bullets: list[str], job_text: str) -> str:
    return PROMPT.format(
        name=name,
        profile=profile_text,
        bullets="\n".join(f"- {b}" for b in bullets[:14]),
        job=job_text,
        max_chars=MAX_SUMMARY_CHARS,
    )
