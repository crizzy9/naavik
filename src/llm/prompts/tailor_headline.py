"""tailor_headline — plan 66 (0.3.1) § T7.

Generates a recruiter-priority one-line headline tailored to the job's
title + specialty signals + (when needed) the candidate's sponsorship
status. Rendered into the top of `onepage_ats.typ` as a 10pt line under
the candidate's 14pt name.

Gated upstream: only invoke when `JobScore.score >= 0.50` (don't tailor
for jobs the candidate won't apply to). Below threshold callers fall
back to `Profile.headline` static value.

Pydantic schema validates total length ≤100 chars + per-chunk ≤30.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

from llm.base import LLMProvider

# Max characters per ` · `-separated chunk + total headline length.
MAX_CHUNK_CHARS = 30
MAX_HEADLINE_CHARS = 100

PROMPT = """Generate a one-line recruiter-priority headline for this candidate × job pair.

Candidate profile:
- Full name: {full_name}
- Existing headline: {existing_headline}
- Summary: {summary}
- Years of experience: {years}
- Work authorization: {work_auth}
- Profile tags: {profile_tags}

Job:
- Role: {role}
- Role family: {role_family}
- Company: {company}
- Description (first 1500 chars):
{description}

Matched tags between candidate and job: {matched_tags}

Compose a TailoredHeadline matching the schema below. The `headline_one_line`
must follow this template:
  "{{title}} · {{years}} yrs · {{specialty}}" + (optional " · {{sponsorship_signal}}")

Total length ≤100 characters; each ` · `-separated chunk ≤30 chars.

Honesty constraints:
- `title` should align with the JD's role but stay true to the candidate's actual seniority.
- `years` must equal the integer years extracted from the candidate's experience.
- `specialty` should call out 1-2 specialty phrases JD-aligned (e.g. "ML platform",
  "distributed systems"). Avoid generic terms like "engineer" or "developer".
- `sponsorship_signal` ONLY when work_authorization indicates a constraint
  (e.g. H1B, OPT_STEM). Sample: "Open to ML/AI roles, H1B+i-140 transfer".
  Leave null when work_auth is GREEN_CARD, US_CITIZEN, or unspecified.

Return a TailoredHeadline.
"""


class TailoredHeadline(BaseModel):
    """Recruiter-priority one-line headline for a tailored resume."""

    title: str = Field(max_length=MAX_CHUNK_CHARS)
    years: int = Field(ge=0, le=50)
    specialty: str = Field(max_length=MAX_CHUNK_CHARS)
    sponsorship_signal: str | None = Field(default=None, max_length=MAX_CHUNK_CHARS + 10)
    # Cap clamps in `_clamp_total_len` (mode="before") so LLM outputs that
    # exceed the cap don't 400 the route — we truncate instead.
    headline_one_line: str
    keywords_emphasized: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("headline_one_line", mode="before")
    @classmethod
    def _clamp_total_len(cls, v: object) -> str:
        s = str(v) if v is not None else ""
        if len(s) > MAX_HEADLINE_CHARS:
            return s[: MAX_HEADLINE_CHARS - 1] + "…"
        return s

    @model_validator(mode="after")
    def _verify_render_shape(self) -> TailoredHeadline:
        """Best-effort consistency check — if the LLM emits a headline that
        doesn't follow the ` · ` template, accept it but cap length."""
        # No hard error: LLMs occasionally rephrase. Just clamp to the cap.
        if len(self.headline_one_line) > MAX_HEADLINE_CHARS:
            self.headline_one_line = self.headline_one_line[: MAX_HEADLINE_CHARS - 1] + "…"
        return self


async def tailor_headline(
    provider: LLMProvider,
    *,
    profile: dict,
    job: dict,
    matched_tags: list[str],
    system: str | None = None,
    cache_system: bool = False,
) -> TailoredHeadline:
    """Invoke the LLM to generate a tailored headline.

    Caller is responsible for gating on `JobScore.score >= 0.50` per T7.
    `system` is the constitution preamble (T3); `cache_system=True` lets
    Anthropic ephemeral-cache the prefix across the bundle's stages.
    """
    rendered = PROMPT.format(
        full_name=profile.get("full_name", ""),
        existing_headline=profile.get("headline", ""),
        summary=(profile.get("summary_full") or profile.get("summary_short") or "")[:600],
        years=profile.get("years_experience", 0),
        work_auth=profile.get("work_authorization") or "unspecified",
        profile_tags=", ".join(profile.get("tags", [])),
        role=job.get("role", ""),
        role_family=job.get("role_family", ""),
        company=job.get("company", ""),
        description=(job.get("description") or "")[:1500],
        matched_tags=", ".join(matched_tags),
    )
    result = await provider.structured(
        rendered,
        TailoredHeadline,
        max_tokens=512,
        system=system,
        cache_system=cache_system,
    )
    return TailoredHeadline.model_validate(result.value)
