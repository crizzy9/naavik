"""draft_scheduling_reply — owner-voice availability reply (plan 96f).

Detect → suggest slots → DRAFT; the owner sends (owner decisions #5/#6 —
Naavik has no send capability, by design and by static guard test). The
draft renders in a panel with Copy + a Gmail compose deep-link; nothing
persists but a NOTE_ADDED AppEvent (auditability without storing prose).
"""

from __future__ import annotations

from pydantic import BaseModel

PROMPT = """You are drafting a short scheduling reply ON BEHALF of a job
seeker, in their voice (first person, warm, direct, no fluff). They are
interviewing with {company}{role_clause}.

The email being answered (latest first):
{conversation}

The job seeker's calendar offers these open slots ({tz_label}):
{slots}

Write ONLY the reply body (no subject line, no signature block beyond a
simple first-name sign-off with "{first_name}"):
- Answer what the sender actually asked ({action_label}).
- Offer the slots naturally in prose or a short list, keeping the
  day/date/time/timezone EXACTLY as given above — never invent or convert
  times.
- 2-5 sentences plus the slot list at most. No pleasantries padding, no
  "I hope this email finds you well".

Return a SchedulingReplyResult JSON object.
"""


class SchedulingReplyResult(BaseModel):
    body: str
