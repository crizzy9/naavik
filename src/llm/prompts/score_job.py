"""score_job — hybrid layered scoring (plan 65 / 0.3.0).

Per BACKEND.md § M.3 + plan 65 § T6. Phase 3 ships the expanded JobScore
shape consumed by `services/scorer/llm_judge.py`. Layer 4 (LLM-as-judge)
is called only when the layer-1 + layer-2 composite clears the
`_LLM_GATE` threshold (0.50). The LLM receives the layer-1/2 scores so it
can calibrate its own grade.

Bounds + length caps prevent prompt-injection oversize-payload attacks.
Validators drop unknown per-dimension keys and truncate strings.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from llm.base import LLMProvider
from models.enums import Tag

# Module-level constants visible to the orchestrator (T6 + T9).
MAX_GAPS = 5
MAX_STRENGTHS = 5
MAX_SUGGESTED_BULLETS = 8
MAX_BULLET_STRING_LENGTH = 120
MAX_VISA_NOTE_LENGTH = 256
MAX_EXPLANATION_LENGTH = 512


PROMPT = """You are an expert technical recruiter scoring how well a candidate matches a job.

Candidate profile:
{profile}

Profile tags (skills the candidate has demonstrated): {profile_tags}

Top relevant bullets (with IDs in brackets — reference by ID in suggested_bullets):
{candidate_bullets}

Job description:
Company: {company}
Role: {role}
Description:
{description}

Job tags (extracted from the description): {job_tags}
Skills required: {skills}
Visa restrictions: {visa_restrictions}

Layer-1 (tag overlap) score: {tag_score:.3f}
Layer-2 (semantic cosine) score: {semantic_score:.3f}

Return a JobScore object matching the schema with:
- `score`: overall match 0.0-1.0
- `explanation`: 1-2 sentences on why (max 512 chars)
- `matched_tags`: tags from {tag_vocabulary} that align between job and candidate
- `per_dimension`: dict of {{tag -> alignment 0.0-1.0}} for each matched tag (max 9 keys)
- `strengths`: 0-5 short bullet strings highlighting fit (max 120 chars each)
- `gaps`: 3-5 short bullet strings of specific skills the candidate lacks (max 120 chars each)
- `suggested_bullets`: list of bullet IDs (integers from the bracketed IDs above) ordered most-relevant-first, max 8
- `visa_concern`: true iff the job requires citizenship/GC and the candidate needs sponsorship
- `visa_note`: short string explaining the visa concern, or null

Be honest about gaps — the candidate uses this to decide whether to apply.
"""


class JobScore(BaseModel):
    """Structured score for a job × profile pairing (plan 65 § T6)."""

    score: float = Field(ge=0.0, le=1.0)
    explanation: str = Field(default="", max_length=MAX_EXPLANATION_LENGTH)
    matched_tags: list[str] = Field(default_factory=list, max_length=9)
    per_dimension: dict[str, float] = Field(default_factory=dict)
    strengths: list[str] = Field(default_factory=list, max_length=MAX_STRENGTHS)
    gaps: list[str] = Field(default_factory=list, max_length=MAX_GAPS)
    suggested_bullets: list[int] = Field(default_factory=list, max_length=MAX_SUGGESTED_BULLETS)
    visa_concern: bool = False
    visa_note: str | None = Field(default=None, max_length=MAX_VISA_NOTE_LENGTH)

    @field_validator("per_dimension", mode="before")
    @classmethod
    def _validate_per_dim(cls, v: dict[str, float] | None) -> dict[str, float]:
        """Drop unknown Tag keys (security) + clamp values to [0, 1]."""
        if not v:
            return {}
        allowed = {t.value for t in Tag}
        out: dict[str, float] = {}
        for k, val in v.items():
            if k not in allowed:
                continue
            try:
                num = float(val)
            except (TypeError, ValueError):
                continue
            out[k] = max(0.0, min(1.0, num))
        return out

    @field_validator("gaps", "strengths", mode="before")
    @classmethod
    def _strip_long_bullets(cls, v: list[str] | None) -> list[str]:
        """Truncate bullet strings to MAX_BULLET_STRING_LENGTH."""
        if not v:
            return []
        return [str(s)[:MAX_BULLET_STRING_LENGTH] for s in v]

    @field_validator("explanation", mode="before")
    @classmethod
    def _coerce_explanation(cls, v: str | None) -> str:
        return str(v) if v is not None else ""


async def score_job(
    provider: LLMProvider,
    *,
    profile: dict[str, Any],
    job: dict[str, Any],
) -> JobScore:
    """Naive end-to-end LLM call (Wave-4 era; kept for direct LLM use cases).

    The layered orchestrator (`services/scorer/orchestrator.py`) is the
    production entry point; this function remains for tests + ad-hoc
    callers that just want the LLM grade without the layers.
    """
    rendered = PROMPT.format(
        profile=(
            f"{profile.get('full_name', '')}\n"
            f"{profile.get('headline', '')}\n"
            f"{profile.get('summary_short') or profile.get('summary_full', '')}"
        ),
        profile_tags="",
        candidate_bullets="",
        company=job.get("company", ""),
        role=job.get("role", ""),
        description=(job.get("description") or "")[:2000],
        job_tags="",
        skills=", ".join(job.get("skills_required", [])),
        visa_restrictions=job.get("visa_restrictions") or "none",
        tag_score=0.0,
        semantic_score=0.0,
        tag_vocabulary=", ".join(t.value for t in Tag),
    )
    result = await provider.structured(rendered, JobScore)
    return JobScore.model_validate(result.value)
