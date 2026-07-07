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

from pydantic import BaseModel, Field, field_validator

from models.enums import Tag

# Module-level constants visible to the orchestrator (T6 + T9).
MAX_GAPS = 5
MAX_STRENGTHS = 5
MAX_SUGGESTED_BULLETS = 8
MAX_BULLET_STRING_LENGTH = 120
MAX_VISA_NOTE_LENGTH = 256
MAX_EXPLANATION_LENGTH = 512

# Plan 86 / 0.4.5.02 — second prompt-caching breakpoint threshold.
# Heuristic: Anthropic tokens ≈ len(text) / 4 chars-per-token. When the
# rendered prompt exceeds ~60K tokens (~240K chars) a second
# `cache_control: ephemeral` breakpoint at the midpoint pays off — the
# fixed-prefix-only cache misses on the bullet corpus that varies between
# users but is stable per user across calls. Below the threshold, the
# single-block cache already covers the whole prompt cheaply.
_CACHE_SECOND_BREAKPOINT_TOKENS = 60_000
_CHARS_PER_TOKEN_ESTIMATE = 4


def should_insert_second_cache_breakpoint(rendered: str) -> bool:
    """True iff the rendered score_job prompt exceeds the 60K-token threshold.

    Plan 86 / 0.4.5.02. Heuristic token count uses `len(rendered) / 4` —
    matches Anthropic's published rough estimate. Boundary cases pinned by
    `test_second_cache_breakpoint_threshold`.
    """
    return (len(rendered) / _CHARS_PER_TOKEN_ESTIMATE) > _CACHE_SECOND_BREAKPOINT_TOKENS


def split_for_double_cache(rendered: str) -> tuple[str, str]:
    """Return (first_half, second_half) of `rendered` for double-cache wiring.

    Split point is the midpoint by length — the actual provider wrapper
    decides whether to attach the second `cache_control` marker. Callers
    should gate this on `should_insert_second_cache_breakpoint(rendered)`.
    """
    mid = len(rendered) // 2
    return rendered[:mid], rendered[mid:]


PROMPT = """You are an expert technical recruiter scoring how well a candidate matches a job.

Candidate profile:
{profile}

Candidate skills inventory — AUTHORITATIVE: the candidate is proficient in
every item listed (the app tracks no proficiency levels); an item on this
list is NEVER a gap and never needs a fluency qualifier:
{skills_inventory}

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
- `strengths`: 0-5 bullet strings (max 120 chars each)
- `gaps`: 0-5 bullet strings (max 120 chars each)
- `suggested_bullets`: list of bullet IDs (integers from the bracketed IDs above) ordered most-relevant-first, max 8
- `visa_concern`: true iff the job requires citizenship/GC and the candidate needs sponsorship
- `visa_note`: short string explaining the visa concern, or null

Rules for `strengths` and `gaps` — these render as a GLANCE VIEW the
candidate scans in seconds, so they are keywords, not prose:
- Each entry is a bare noun phrase of at most 6 words naming the specific
  skill/technology/theme from the JD: "distributed systems",
  "Cypress E2E testing", "campaign platform architecture".
- NO sentences. NO verbs like built/led/shipped. NO "JD"/"candidate"
  phrasing, no verdict text, no trailing periods.
- A strength names a JD theme the candidate's record clearly covers; a gap
  names a JD ask with NO evidence anywhere in the profile.
- The skills inventory above is authoritative — never list an inventory
  item as a gap and never qualify anything with proficiency/fluency
  wording.
- Deduplicate: one entry per distinct theme; an item appears in strengths
  OR gaps, never both.
- Fewer, sharper entries beat five vague ones. Zero gaps is acceptable for
  a genuinely dead-on match; zero strengths for a genuinely bad one.

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
