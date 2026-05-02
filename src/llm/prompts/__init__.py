"""Prompt module skeletons + Pydantic schemas.

Per plan 10 § B.4 + BACKEND.md § M.3. Wave 4 ships the module skeletons +
schemas + a working `score_job` (real-but-naive). The full prompt pipelines
(extraction, bullet selection, cover letter, etc.) wire in Wave 6.

Each prompt module exposes:
- A versioned `PROMPT` template string
- A Pydantic schema for the structured response
- An async `<name>(provider, ...)` callable returning the schema instance
"""

from __future__ import annotations

from .answer_screener import ScreenerAnswer, answer_screener
from .auto_tag_bullets import BulletTags, auto_tag_bullets
from .classify_email import EmailClassificationResult, classify_email
from .draft_cover_letter import CoverLetterDraft, draft_cover_letter
from .draft_outreach import OutreachDraft, draft_outreach
from .extract_job import ExtractedJob, extract_job
from .extract_resume import ExtractedResume, extract_resume
from .score_job import JobScore, score_job
from .select_bullets import BulletSelection, select_bullets
from .trim_bullet import TrimmedBullet, trim_bullet

__all__ = [
    "BulletSelection",
    "BulletTags",
    "CoverLetterDraft",
    "EmailClassificationResult",
    "ExtractedJob",
    "ExtractedResume",
    "JobScore",
    "OutreachDraft",
    "ScreenerAnswer",
    "TrimmedBullet",
    "answer_screener",
    "auto_tag_bullets",
    "classify_email",
    "draft_cover_letter",
    "draft_outreach",
    "extract_job",
    "extract_resume",
    "score_job",
    "select_bullets",
    "trim_bullet",
]
