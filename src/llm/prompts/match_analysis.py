"""match_analysis — purpose-specific review-panel analysis (2026-07).

Runs lazily the first time a job's review workspace opens (persisted into
`Job.match_breakdown`), separate from the score_job judge call. Two jobs:

1. Per-requirement coverage marks for the WHAT THEY WANT column — replaces
   the token-overlap heuristic that left obviously-covered asks ("Senior
   software engineering experience") unmarked.
2. Glance-view keyword strengths/gaps — replaces the fluffy
   "JD wants X — candidate shipped Y" sentences that overflowed the panel.

The skills inventory is AUTHORITATIVE: the app has no proficiency levels,
so every listed skill counts as proficient and can never be a gap.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

MAX_REQUIREMENTS = 16
MAX_KEYWORDS = 5
MAX_KEYWORD_CHARS = 60

PROMPT = """You are auditing how a candidate's profile covers a job's stated requirements.

Job:
Company: {company}
Role: {role}
Description (excerpt):
{description}

The job's requirement list (index → text):
{requirements}

Candidate skills inventory — AUTHORITATIVE: the candidate is proficient in
every item listed; an item on this list is NEVER missing and NEVER a gap:
{skills_inventory}

Candidate titles held (most recent first): {titles}

Total professional experience: {years_experience} (computed from employment
dates — use THIS number for any "N+ years" ask, not guesses from prose).

Candidate summary:
{summary}

Candidate experience bullets:
{bullets}

Return MatchAnalysis with:

1. `requirements` — one entry per requirement index, with `covered`:
   - covered=true when the skills inventory, bullets, summary, or titles
     evidence it — directly or via a clear equivalent.
   - Seniority asks ("senior experience") are covered when the titles/
     history show that level — a Senior title covers "senior software
     engineering experience". "N+ years" asks are covered when the
     computed total experience above is ≥ N.
   - Generic engineering-practice asks (testing, code review, CI/CD,
     mentoring, cross-functional work) are covered when any bullet or skill
     shows them in practice; do not demand the exact JD wording.
   - covered=false ONLY when nothing in the profile evidences it (a domain,
     clearance, credential, location constraint, or technology entirely
     absent).

2. `strengths` (max {max_keywords}) and `gaps` (max {max_keywords}) — GLANCE-VIEW KEYWORDS:
   - Each entry is a bare noun phrase, at most 6 words, naming the
     skill/theme: "distributed systems", "Cypress E2E testing",
     "campaign platform architecture".
   - NO sentences. NO verbs like built/led/shipped. NO "JD"/"candidate"
     phrasing. NO explanations, verdicts, or trailing periods.
   - A strength names a JD theme the profile clearly covers; a gap names a
     JD ask with no profile evidence at all.
   - NEVER put anything from the skills inventory in gaps; never use
     proficiency/fluency wording anywhere.
   - An item appears in strengths OR gaps, never both. Fewer, sharper
     entries beat five vague ones.
"""


class RequirementCoverage(BaseModel):
    index: int = Field(ge=0, lt=MAX_REQUIREMENTS)
    covered: bool


class MatchAnalysis(BaseModel):
    requirements: list[RequirementCoverage] = Field(
        default_factory=list, max_length=MAX_REQUIREMENTS
    )
    strengths: list[str] = Field(default_factory=list, max_length=MAX_KEYWORDS)
    gaps: list[str] = Field(default_factory=list, max_length=MAX_KEYWORDS)

    @field_validator("strengths", "gaps", mode="before")
    @classmethod
    def _keywordize(cls, v: list[str] | None) -> list[str]:
        """Trim, cap length, drop empties/dupes — glance-view hygiene."""
        if not v:
            return []
        out: list[str] = []
        seen: set[str] = set()
        for raw in v:
            s = " ".join(str(raw).split()).strip(" .;:—–-")[:MAX_KEYWORD_CHARS].strip()
            if not s or s.lower() in seen:
                continue
            seen.add(s.lower())
            out.append(s)
        return out[:MAX_KEYWORDS]
