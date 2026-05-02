"""draft_outreach — Phase 5 wires this end-to-end.

Per BACKEND.md § H.1, § M.3.
"""

from __future__ import annotations

from pydantic import BaseModel

from llm.base import LLMProvider

PROMPT = """Draft an outreach message.

Sender:
{sender_profile}

Recipient:
{recipient}

Intent: {intent}
Channel: {channel}
{context}

Return OutreachDraft with subject (email only) and body. Tone: warm but
professional. Length: 60–150 words. Reference specific mutual context if
provided.
"""


class OutreachDraft(BaseModel):
    subject: str = ""
    body: str


async def draft_outreach(
    provider: LLMProvider,
    *,
    sender_profile: dict,
    recipient: dict,
    intent: str,
    channel: str = "linkedin_dm",
    context: str = "",
) -> OutreachDraft:
    rendered = PROMPT.format(
        sender_profile=f"{sender_profile.get('full_name')}\n{sender_profile.get('summary_short') or ''}",
        recipient=f"{recipient.get('name')} ({recipient.get('title')} at {recipient.get('company')})",
        intent=intent,
        channel=channel,
        context=context or "(no extra context)",
    )
    result = await provider.structured(rendered, OutreachDraft, max_tokens=512)
    return OutreachDraft.model_validate(result.value)
