"""refine_bullet — item 2 (2026-07): rewrite a bullet AGAINST the JD.

Supersedes the plain length trim in the resume pipeline: every selected
bullet is rewritten to mirror the job description's terminology where —
and only where — the underlying fact already supports it. Hard honesty
constraints: never invent facts, numbers, technologies, or scope.
"""

from __future__ import annotations

from pydantic import BaseModel

PROMPT = """You are refining ONE resume bullet for a specific job application.

Job description (excerpt):
{job_text}

Original bullet (the source of truth — every claim must trace back to it):
{text}

Rewrite the bullet so it speaks the job description's language:
- Where the original and the JD describe the same thing with different
  words, prefer the JD's term (e.g. original "message queue pipeline" +
  JD "event streaming" → "event streaming pipeline" IF that is what it was).
- Lead with the strongest verb; keep the most concrete result.
- At most {target_chars} characters — it must fit ONE printed line.

HARD HONESTY CONSTRAINTS — violating any of these is a failure:
- Never invent facts, metrics, numbers, team sizes, or outcomes.
- Never name a technology, tool, or methodology that is not in the
  original bullet.
- Never inflate scope (e.g. "led" only if the original says led/managed).
- If the JD's terminology does not truthfully describe the work, keep the
  original wording.

Return RefinedBullet with `refined` (the rewritten one-line bullet) and
`jd_terms_used` (JD terms you mirrored, empty list if none applied).
"""


class RefinedBullet(BaseModel):
    refined: str
    jd_terms_used: list[str] = []
