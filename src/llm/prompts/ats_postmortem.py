"""ats_postmortem — LLM-output schema + prompt template for ATS failure diagnosis.

Per docs/plans/52-0.2.3.02-postmortem-on-failure.md § D.1. Used by
`services/ats_postmortem.capture_postmortem` to classify + summarize an ATS
submission failure from its HTTP request/response trace.

`PostmortemAnalysis.failure_kind` mirrors `services/ats/base.FAILURE_*`.
Bounded string lengths cap LLM prompt-injection blast radius (plan § Risk).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PostmortemAnalysis(BaseModel):
    """LLM-output schema for `services/ats_postmortem.capture_postmortem`."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    failure_kind: Literal["captcha", "rate_limit", "auth_required", "field_mismatch", "unknown"]
    summary: str = Field(min_length=1, max_length=600)
    suggested_action: str = Field(min_length=1, max_length=400)


PROMPT = """You are diagnosing an ATS submission failure. Given the request/response trace
below, classify the failure_kind, write a 1-2 sentence summary, and a single
suggested_action (operator-facing, plain English, no jargon).

TRACE:
{trace_json}

Classify failure_kind as ONE of:
- captcha          - response indicates a CAPTCHA / bot challenge
- rate_limit       - HTTP 429 or rate-limit text in the body
- auth_required    - HTTP 401/403 or session/cookie expired
- field_mismatch   - HTTP 422 or schema/validation errors in the body
- unknown          - anything else, or the trace is too sparse to classify

Return ONLY a PostmortemAnalysis JSON object.
"""


__all__ = ["PROMPT", "PostmortemAnalysis"]
