"""Hiring manager extractor — plan 66 (0.3.1) § T11.

Regex-first + LLM-fallback + UI manual override. Regex patterns cover
the most common JD phrasings (~70% recall in the SOTA research memo's
corpus). When regex misses AND the JD is ≥200 chars, fall back to a
single structured LLM call.

The UI manual-override path bypasses both: the bundle endpoint accepts
a `hiring_manager_override: str | None = None` kwarg; when set, returns
`{name, source: "manual", confidence: 1.0}` directly.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from llm import LLMProviderError, get_provider
from llm.base import LLMProvider
from models import Settings
from services import llm_tracker

log = logging.getLogger(__name__)

# Regex patterns ordered by specificity — first match wins.
_PATTERNS: list[re.Pattern] = [
    # "Hiring Manager: Jane Smith"
    re.compile(r"Hiring\s+Manager:\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})"),
    # "Reporting to Jane Smith"
    re.compile(r"\bReporting\s+to\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})"),
    # "You'll report to Jane Smith" / "You will report to ..."
    re.compile(r"You'?ll\s+report\s+to\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})"),
    re.compile(r"You\s+will\s+report\s+to\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})"),
    # "Manager: Jane Smith"
    re.compile(r"\bManager:\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})"),
    # "Contact: Jane Smith"
    re.compile(r"\bContact:\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})"),
]


@dataclass(slots=True)
class HiringManagerHit:
    """Extracted hiring manager metadata for a JD.

    `source` ∈ {"regex", "llm", "manual"}; `confidence` ∈ [0.0, 1.0].
    The cover letter renderer uses `name` directly in the salutation
    when `confidence >= 0.5`.
    """

    name: str
    title: str | None
    source: Literal["regex", "llm", "manual"]
    confidence: float


class _HiringManagerSchema(BaseModel):
    """LLM-fallback structured output."""

    name: str | None = None
    title: str | None = None
    confidence: float = 0.5


_LLM_PROMPT = """Extract the hiring manager's name + title from this job
description, if mentioned. Look for explicit phrasings like "Hiring Manager:
<name>", "Reporting to <name>", "You'll report to <name>", or a contact
person's full name.

If no hiring manager is mentioned (or only a generic role like "Hiring Team"
is named), return name=null + confidence=0.0.

Job description:
{description}

Return a _HiringManagerSchema with name (or null), title (or null), and
confidence (0.0-1.0).
"""


def _try_regex(description: str) -> HiringManagerHit | None:
    """Run all regex patterns; return the first hit (or None)."""
    if not description:
        return None
    for pattern in _PATTERNS:
        match = pattern.search(description)
        if match:
            name = match.group(1).strip()
            return HiringManagerHit(
                name=name,
                title=None,
                source="regex",
                confidence=0.90,
            )
    return None


async def _try_llm_fallback(
    session: AsyncSession,
    *,
    user_id: int,
    provider: LLMProvider,
    description: str,
    application_id: int | None = None,
) -> HiringManagerHit | None:
    """Single structured LLM call. Returns None on failure or no-hit."""
    try:
        result = await llm_tracker.tracked_call(
            session=session,
            user_id=user_id,
            provider=provider,
            method="structured",
            prompt_name="extract_hiring_manager",
            application_id=application_id,
            prompt=_LLM_PROMPT.format(description=description[:3000]),
            schema=_HiringManagerSchema,
        )
        data = result.value if hasattr(result, "value") else result
        if not isinstance(data, dict):
            return None
        name = data.get("name")
        if not name or not isinstance(name, str) or not name.strip():
            return None
        return HiringManagerHit(
            name=name.strip(),
            title=(data.get("title") or None),
            source="llm",
            confidence=max(0.0, min(1.0, float(data.get("confidence", 0.5)))),
        )
    except LLMProviderError as exc:
        log.warning("hiring_manager LLM fallback failed: %s", exc)
        return None


async def extract_hiring_manager(
    session: AsyncSession,
    *,
    user_id: int,
    settings: Settings,
    job_description: str,
    application_id: int | None = None,
    manual_override: str | None = None,
) -> HiringManagerHit | None:
    """Extract hiring manager from JD with regex-first + LLM-fallback.

    `manual_override` short-circuits both — returns
    `{name, source: "manual", confidence: 1.0}` directly. Pass None /
    "" / whitespace-only to skip the override.
    """
    if manual_override and manual_override.strip():
        return HiringManagerHit(
            name=manual_override.strip(),
            title=None,
            source="manual",
            confidence=1.0,
        )

    desc = job_description or ""
    regex_hit = _try_regex(desc)
    if regex_hit is not None:
        return regex_hit

    if len(desc) < 200:
        return None

    provider = get_provider(settings)
    return await _try_llm_fallback(
        session,
        user_id=user_id,
        provider=provider,
        description=desc,
        application_id=application_id,
    )
