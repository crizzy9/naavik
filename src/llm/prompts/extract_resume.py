"""extract_resume — Wave 6 wires this end-to-end (Onboarding step 2).

Per BACKEND.md § M.3. Wave 4 ships the schema skeleton.

All list fields carry fully-typed item models (no bare `dict`) — OpenAI's
strict json_schema mode rejects free-form objects, and typed shapes give
the extractor model an explicit contract that maps 1:1 onto the Skill /
Education / Project rows persisted by `services.profile.extraction._persist_profile`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

# Keep in sync with `ui/templates_setup.TAG_VOCAB` + CLAUDE.md § Resume/CV
# Data Model (the canonical 9-tag vocabulary).
TAG_VOCAB = (
    "ai-ml",
    "backend",
    "frontend",
    "devops",
    "data-eng",
    "genai",
    "leadership",
    "platform",
    "product",
)

PROMPT = """Extract a candidate profile from this resume PDF text.

Resume text:
{resume_text}

Return ExtractedResume with full_name, headline, location, email, phone,
linkedin_handle, github_handle, portfolio_url, summary_full (the resume's
summary/objective paragraph verbatim, if any), summary_short (<= 25 words),
experiences[], skills[], educations[], projects[], and certifications[].

Rules:
- Each experience carries bullets[] — the FULL text of each achievement
  bullet, one entry per bullet, preserving numbers and verbs.
- bullet_tags[] is parallel to bullets[]: for each bullet, choose 1-3 tags
  from exactly this vocabulary: {tag_vocab}.
- projects[] covers BOTH a "Projects" section and an "Open Source
  Contributions" (or similar) section. Set kind="project" for personal /
  academic / work projects and kind="open_source" for entries under an
  open-source / OSS-contributions heading. Keep each entry's one-line
  description (if any) in text.
- certifications[] captures a "Certifications" / "Licenses" section. Split
  entries like "AWS Certified Solutions Architect - Amazon" into title and
  issuer; leave issuer "" when the resume names none.
- Dates are ISO strings: "YYYY-MM-DD", "YYYY-MM", or "YYYY". Use null for
  "Present"/current roles.
- skills[] groups the resume's skill lines as {{category, items[]}}
  (e.g. category "Languages", items ["Python", "Go"]).
- linkedin_handle / github_handle are the BARE handles (e.g. "shyampadia"
  from linkedin.com/in/shyampadia, "crizzy9" from github.com/crizzy9) —
  strip any URL prefix. portfolio_url is a personal website / portfolio
  domain (e.g. "crypticsoul.dev"); use null when absent. Resume headers
  often list these as plain text or hyperlinks near the contact line.
- Do not invent content that is not in the resume text.
"""


class ExtractedExperience(BaseModel):
    company: str
    title: str
    team: str | None = None
    location: str | None = None
    start_date: str | None = None  # ISO date string
    end_date: str | None = None
    bullets: list[str] = []
    bullet_tags: list[list[str]] = []  # parallel to bullets


class ExtractedSkillGroup(BaseModel):
    category: str
    items: list[str] = []


class ExtractedEducation(BaseModel):
    institution: str
    degree: str
    location: str | None = None
    start_date: str | None = None  # ISO date string
    end_date: str | None = None
    gpa: str | None = None
    courses: list[str] = []


class ExtractedProject(BaseModel):
    title: str
    text: str = ""  # one-line description / achievement text
    date: str | None = None  # ISO date string
    tags: list[str] = []
    link: str | None = None
    # "project" | "open_source" — mirrors Project.kind; OSS-contribution
    # sections land as kind="open_source" so they render as their own block.
    kind: Literal["project", "open_source"] = "project"


class ExtractedCertification(BaseModel):
    title: str
    issuer: str = ""
    date: str | None = None  # ISO date string
    description: str | None = None


class ExtractedResume(BaseModel):
    full_name: str
    headline: str | None = None
    location: str | None = None
    email: str | None = None
    phone: str | None = None
    linkedin_handle: str | None = None
    github_handle: str | None = None
    portfolio_url: str | None = None
    summary_full: str | None = None
    summary_short: str | None = None
    experiences: list[ExtractedExperience] = []
    skills: list[ExtractedSkillGroup] = []
    educations: list[ExtractedEducation] = []
    projects: list[ExtractedProject] = []
    certifications: list[ExtractedCertification] = []
