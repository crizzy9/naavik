"""expand_titles — LLM-output schema + prompt for target-title expansion.

Per docs/design/JOB_SEARCH_PREFERENCES.md § F. Each profile-level target
title (e.g. "Senior Software Engineer") expands to a set of equivalent
titles/levels companies actually use ("Software Engineer III", "SDE III",
"Staff Software Engineer", ...). Expansions are stored on
`Profile.title_expansions` and used for post-fetch title matching in the
scorer + Discover ordering; the raw titles drive the search queries.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_EXPANSIONS_PER_TITLE = 12


class TitleExpansion(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1)
    expanded: list[str] = Field(default_factory=list)

    @field_validator("expanded")
    @classmethod
    def _cap_and_clean(cls, v: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for item in v:
            item = item.strip()
            key = item.lower()
            if item and key not in seen:
                seen.add(key)
                out.append(item)
        return out[:MAX_EXPANSIONS_PER_TITLE]


class TitleExpansions(BaseModel):
    """LLM-output schema for `services/search_prefs.refresh_title_expansions`."""

    model_config = ConfigDict(extra="forbid")

    expansions: list[TitleExpansion] = Field(default_factory=list)


PROMPT = """You are helping a job-search tool match job postings to a candidate's target roles.

Candidate headline: {headline}

Target titles:
{titles}

For EACH target title, list the equivalent job titles and level-variants that
different companies use for the same role. Include:
- level-scheme variants (e.g. "Senior Software Engineer" ~ "Software Engineer III" ~ "SDE III" ~ "Software Engineer 3")
- common abbreviations and spellings ("Sr. Software Engineer", "Senior SWE")
- close synonyms for the same job function ("ML Engineer" ~ "Machine Learning Engineer" ~ "MLE")

Rules:
- Max {max_expansions} expansions per title; most common first.
- Only titles for the SAME role and seniority band — do not drift up
  (e.g. no "Principal" for a "Senior" target) or sideways into different
  functions (no "Data Scientist" for "ML Engineer").
- Include the original title itself as the first entry.
- Return one TitleExpansion per input title, in the same order.
"""


def render_prompt(*, titles: list[str], headline: str | None) -> str:
    return PROMPT.format(
        headline=headline or "(none)",
        titles="\n".join(f"- {t}" for t in titles),
        max_expansions=MAX_EXPANSIONS_PER_TITLE,
    )


__all__ = [
    "MAX_EXPANSIONS_PER_TITLE",
    "PROMPT",
    "TitleExpansion",
    "TitleExpansions",
    "render_prompt",
]
