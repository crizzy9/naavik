"""draft_email_response — plan 90 (0.5.0.06) scaffold.

Stub-but-working: handles three intents (`reply`, `schedule_interview`,
`decline`) with a minimal prompt + Pydantic schema. The send wire is OUT
of scope for this plan (`0.5.0.06a` modal + `0.5.0.06b` SMTP).

LLM call MUST flow through `services.llm_tracker.tracked_call` per
`engineer-llm-tracker-wrap`.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from llm.base import LLMProvider
from services import llm_tracker

PROMPT = """Draft a concise email reply on behalf of a job applicant.

Original sender: {sender}
Subject: {subject}
Recent message preview (200 chars):
{recent_snippet}

Intent: {intent}

Return DraftEmailResponse with:
- `subject` (one short line; prefix "Re: " if a thread reply)
- `body` (3-6 sentences, professional but warm; never overstate timeline
  certainty; sign off as the applicant)

Style guardrails:
- No "I am writing to" filler.
- No exclamation points.
- Acknowledge the sender by first name if known.
- For `reply` intent: thank, confirm, propose a next step.
- For `schedule_interview`: confirm interest, offer 2-3 time windows next week.
- For `decline`: gracious decline, leave door open.
"""


Intent = Literal["reply", "schedule_interview", "decline", "follow_up"]


class DraftEmailResponse(BaseModel):
    subject: str
    body: str


async def draft_email_response(
    provider: LLMProvider,
    *,
    session: AsyncSession | None = None,
    user_id: int,
    subject: str,
    sender: str,
    recent_snippet: str,
    intent: Intent = "reply",
    **extra: Any,
) -> DraftEmailResponse:
    rendered = PROMPT.format(
        sender=sender,
        subject=subject,
        recent_snippet=recent_snippet[:200],
        intent=intent,
    )
    result = await llm_tracker.tracked_call(
        session=session,
        user_id=user_id,
        provider=provider,
        method="structured",
        prompt_name="draft_email_response",
        prompt=rendered,
        schema=DraftEmailResponse,
        max_tokens=512,
    )
    value = getattr(result, "value", None) or result
    if isinstance(value, DraftEmailResponse):
        return value
    return DraftEmailResponse.model_validate(value)
