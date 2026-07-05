"""classify_email — Phase 4 wires this end-to-end.

Per BACKEND.md § H.1, § M.3.
"""

from __future__ import annotations

from pydantic import BaseModel

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
