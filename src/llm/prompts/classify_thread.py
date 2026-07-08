"""classify_thread — conversation-coherent read of an application's email.

Plan 96e (owner decision #12): the reconciler's LLM pass. Where the
per-message classifier sees isolated snippets, this reads the application's
WHOLE correspondence (every signal conversation, newest-first,
excerpt-capped) in ONE call and answers what the process has actually
reached, the CANONICAL list of concrete interviews it contains (the owner's
itemized-rounds model, 2026-07-08 — every distinct interview is its own
round even when several share one calendar event), whether it ended in a
rejection, and whether the ball is in the job seeker's court to schedule.

Deviation from the plan's per-thread sketch (logged): independent per-thread
calls described the same process from partial views and their outputs merged
into duplicate rounds — one application-level call dedupes where the
context lives, and costs less.

Deterministic code decides what to DO with the answers (round adopt/rewrite,
container time anchoring, forward-only stage diff, CLOSED stays
human-confirm) — the LLM never mutates pipeline state.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

PROMPT = """You are reading a job seeker's email correspondence about their
application to {company}{role_clause}. Below are the conversations, newest
message first within each. Read them TOGETHER and answer about the ONE
interview process they evidence.

{conversation}

Answer:
- process_stage: the furthest stage the correspondence shows the process has
  REACHED — "screen" (recruiter/phone screen scheduled or done),
  "interview" (technical / onsite / any round past the first screen), or
  "offer". null when it shows none of these.
- rounds: the COMPLETE, DEDUPLICATED list of concrete interviews the
  correspondence describes, one entry per distinct interview — itemize
  agenda segments separately even when several happen inside one calendar
  event or one day (e.g. "2:00 Coding with Alex, 3:00 System Design with
  Leon" is TWO rounds), and merge invitations / confirmations / reminders
  of the SAME interview into ONE entry even when they arrived in different
  conversations. For each:
  - kind: one of "recruiter_screen", "technical_screen", "take_home",
    "system_design", "hiring_manager", "builder_interview", "team_match",
    "panel", "onsite_loop", or "other" for a named round that fits none.
  - title: the interview's name as the correspondence phrases it (e.g.
    "WHO Interview", "Coding Project"), null when unnamed.
  - interviewer: the INTERVIEWER's name when stated, else null — never the
    job seeker themselves (the person this inbox belongs to).
  - date: the interview's calendar date as YYYY-MM-DD when stated, else
    null.
  - time: the interview's start time as HH:MM (24h, in whatever timezone
    the text states) when given, else null.
  - state: "completed" ONLY when the interview's date is in the past or a
    message explicitly says it happened; "scheduled" when it has a
    confirmed date/time; else "planned".
  Only interviews the correspondence actually describes — never invent a
  "typical" process.
- rejection: true ONLY when the correspondence says the company is not
  moving forward (declined, position filled, failed a round) and no LATER
  message shows the process continued.
- needs_scheduling: true ONLY when the LATEST ball is in the job seeker's
  court to schedule — the company asked for availability, sent a booking
  link the correspondence does not show as booked, or proposed times
  awaiting confirmation.

Return a ThreadReconcileResult JSON object.
"""


class ThreadRound(BaseModel):
    kind: str
    title: str | None = None
    interviewer: str | None = None
    date: str | None = None
    time: str | None = None
    state: str = "planned"


class ThreadReconcileResult(BaseModel):
    process_stage: str | None = None
    rounds: list[ThreadRound] = Field(default_factory=list)
    rejection: bool = False
    needs_scheduling: bool = False
