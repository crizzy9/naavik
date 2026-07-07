"""parse_interview_plan — recruiter notes → expected interview rounds.

Plan 95 § 3.1 producer 2: the owner pastes recruiter-screen notes into the
application's notes field and clicks "Parse interview plan" (explicit,
preview-before-save — notes may contain anything, so parsing NEVER runs on
save). One structured call projects the expected rounds as `state=planned`
rows; emails and calendar events then check them off.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

PROMPT = """You are reading a job seeker's notes about an interview process
at {company} to extract the EXPECTED interview rounds ("process map").

Notes:
{notes}

Extract the ordered list of interview rounds the notes describe. For each:
- kind: one of "recruiter_screen", "technical_screen", "take_home",
  "system_design", "hiring_manager", "builder_interview", "team_match",
  "panel", "onsite_loop" (a bundled block of several back-to-back
  interviews treated as one gate), or "other" for a named round that fits
  none of these.
- title: the round's name as the notes phrase it (e.g. "Virtual System
  Design Exercise"), null when the notes give no specific name.
- sessions: ONLY for kind=onsite_loop — the itemized sub-interviews when the
  notes list them (e.g. ["Coding", "System design", "Behavioral with HM"]);
  empty list otherwise.

Rules:
- Only rounds the notes actually describe — never invent a "typical"
  process.
- Rounds that already happened still count (they will be checked off).
- If the notes describe no interview process at all, return an empty list.

Return an InterviewPlanResult JSON object.
"""


class PlannedRound(BaseModel):
    kind: str
    title: str | None = None
    sessions: list[str] = Field(default_factory=list)


class InterviewPlanResult(BaseModel):
    rounds: list[PlannedRound] = Field(default_factory=list)
