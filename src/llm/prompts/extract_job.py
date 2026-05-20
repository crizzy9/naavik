"""extract_job — LLM-output schema + prompt template for AI job extraction.

Per docs/design/JOB_EXTRACTION.md (graduated from plan 30 / 0.2.0.08).

`JobExtraction` is a strict subset of the AI-refined columns in `RawJob`
(per docs/design/SCRAPER_BASE.md § D.1), plus three scorer-required `Job`
fields (`skills_required` / `criteria` / `tags`) the LLM is the sole
authoritative writer of.

Scraper-owned identity fields (`source` / `external_id` / `source_url` /
`board` / `url_type` / `raw_meta`) are NOT in this schema — the extractor
service (`src/services/job_extractor.py:enrich_raw_job`) re-supplies them
when building the enriched `RawJob`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from models.enums import RemotePolicy, SeniorityLevel, VisaRestriction

# Closed vocabulary mirrored from `models.enums.Tag` + the 9-tag rule in
# AGENTS.md § Key Conventions § Resume/CV Data Model. LLM outputs that
# carry off-vocab strings now fail Pydantic validation at the boundary
# (plan 46 / 0.2.0.08a — fail-fast on LLM hallucination per filed
# hacker review on PR #106).
TagLiteral = Literal[
    "ai-ml",
    "backend",
    "frontend",
    "devops",
    "data-eng",
    "genai",
    "leadership",
    "platform",
    "product",
]


class JobExtraction(BaseModel):
    """LLM-output schema for `services/job_extractor.enrich_raw_job`."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    # Normalized identity (overwrites scraper's best-effort reads)
    company_name: str = Field(min_length=1)
    position_title: str = Field(min_length=1)

    # Normalized location + structured time
    location_raw: str | None = None
    posted_at_text: str | None = None
    posted_at: str | None = None  # ISO 8601 string; service parses to datetime

    # Salary — LLM returns parsed bounds + raw passthrough
    salary_raw: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None

    # Structured signals — overwrites RawJob `*_hint` trio with authoritative read
    remote_policy: RemotePolicy = RemotePolicy.UNKNOWN
    visa_restrictions: VisaRestriction = VisaRestriction.NOT_MENTIONED
    seniority_level: SeniorityLevel | None = None

    # Plain-text body (LLM strips boilerplate / normalizes whitespace)
    description: str = Field(min_length=1)

    # Scorer-required arrays (LLM is sole writer)
    criteria: list[str] = Field(default_factory=list)
    skills_required: list[str] = Field(default_factory=list)
    tags: list[TagLiteral] = Field(default_factory=list)


PROMPT = """Extract structured job information from this job description.

Input:
{html}

Return a JobExtraction with these fields:

- company_name: Hiring company name. Normalize ("Anthropic, PBC" -> "Anthropic"; "Stripe Inc." -> "Stripe").
- position_title: Job title. Normalize abbreviations ("Sr. SWE" -> "Senior Software Engineer"; "SDE II" -> "Software Engineer II").
- location_raw: Job location as written (e.g. "San Francisco, CA" or "Remote - US" or "London, UK"). null if absent.
- posted_at_text: Verbatim "posted X days ago" / "posted on Jan 5, 2026" string if present. null if absent.
- posted_at: ISO 8601 date if you can derive it from posted_at_text (e.g. "Posted 3 days ago" + today -> ISO date). null if you can't.
- salary_raw: Verbatim salary string from the JD (e.g. "$180k-$240k base + equity"). null if absent.
- salary_min: Parsed lower bound in USD/year. null if missing or not USD.
- salary_max: Parsed upper bound in USD/year. null if missing or not USD.
- remote_policy: ONE of:
    - "remote" - fully remote
    - "hybrid" - 1-3 days in office expected
    - "onsite" - 4-5 days in office
    - "unknown" - JD doesn't say (default)
- visa_restrictions: ONE of:
    - "us_citizen_only" - JD requires US citizenship
    - "green_card_required" - JD requires green card / permanent residency
    - "sponsorship_available" - JD explicitly offers H1B / visa sponsorship
    - "not_mentioned" - JD does not say (default)
- seniority_level: ONE of: "entry" / "mid" / "senior" / "staff" / "principal" / "exec" / "unknown". null if you can't tell.
- description: Plain-text job description, with HTML stripped, sections preserved as headings ("Required:", "Nice to have:", "About the role:"). Trim boilerplate footers / equal opportunity statements.
- criteria: list of hard requirements ("5+ years experience", "Bachelor's degree in CS", "must be authorized to work in US"). Concise; one bullet per criterion.
- skills_required: list of named skills / technologies / frameworks ("Python", "Kubernetes", "PostgreSQL", "Distributed systems"). Lowercase singular nouns where natural.
- tags: list of broad categorical tags from this fixed vocabulary: ["ai-ml", "backend", "frontend", "devops", "data-eng", "genai", "leadership", "platform", "product"]. Choose 2-4 tags. Use only this vocabulary.

If a field is missing or ambiguous in the JD, use the schema's documented default rather than guessing.
"""


__all__ = ["PROMPT", "JobExtraction", "TagLiteral"]
