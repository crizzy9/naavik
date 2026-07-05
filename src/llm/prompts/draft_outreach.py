"""draft_outreach — Phase 5 wires this end-to-end.

Per BACKEND.md § H.1, § M.3.
"""

from __future__ import annotations

from pydantic import BaseModel

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
