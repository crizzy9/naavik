"""Prompt module skeletons + Pydantic schemas.

Per plan 10 § B.4 + BACKEND.md § M.3. Wave 4 ships the module skeletons +
schemas + a working `score_job` (real-but-naive). The full prompt pipelines
(extraction, bullet selection, cover letter, etc.) wire in Wave 6.

Each prompt module exposes a versioned `PROMPT` template string and a
Pydantic schema for the structured response; services invoke them through
`services.llm_tracker.tracked_call` (the bare async convenience wrappers
were tracker-bypass traps with zero callers — deleted in plan 91 5.3/6.4).
"""

from __future__ import annotations

from .answer_screener import ScreenerAnswer
from .auto_tag_bullets import BulletTags
from .classify_email import EmailClassificationResult
from .draft_cover_letter import CoverLetterDraft
from .draft_cover_letter_sota import (
    CoverLetterSota,
    detect_pain_letter_format,
)
from .draft_outreach import OutreachDraft
from .extract_job import PROMPT as EXTRACT_JOB_PROMPT
from .extract_job import JobExtraction
from .extract_resume import ExtractedResume
from .score_job import JobScore
from .select_bullets import BulletSelection
from .trim_bullet import TrimmedBullet

__all__ = [
    "BulletSelection",
    "BulletTags",
    "CoverLetterDraft",
    "CoverLetterSota",
    "EmailClassificationResult",
    "EXTRACT_JOB_PROMPT",
    "ExtractedResume",
    "JobExtraction",
    "JobScore",
    "OutreachDraft",
    "ScreenerAnswer",
    "TrimmedBullet",
    "detect_pain_letter_format",
]
