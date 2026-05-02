"""classify_email — Phase 4 wires this end-to-end.

Per BACKEND.md § H.1, § M.3.
"""

from __future__ import annotations

from pydantic import BaseModel

from llm.base import LLMProvider

PROMPT = """Classify this email about a job application.

From: {sender}
Subject: {subject}
Body:
{body}

Return EmailClassificationResult with `classification` (one of
INTERVIEW_REQUEST | REJECTION | OFFER | ASSESSMENT | FOLLOW_UP | OTHER) and
`urgency` (high / medium / low).
"""


class EmailClassificationResult(BaseModel):
    classification: str
    urgency: str = "medium"


async def classify_email(
    provider: LLMProvider,
    *,
    sender: str,
    subject: str,
    body: str,
) -> EmailClassificationResult:
    rendered = PROMPT.format(sender=sender, subject=subject, body=body[:4000])
    result = await provider.structured(rendered, EmailClassificationResult, max_tokens=256)
    return EmailClassificationResult.model_validate(result.value)
