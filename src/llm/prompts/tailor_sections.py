"""tailor_sections — per-job selection of Skills items + Project rows.

Work experience is the core of the resume; Skills and Projects flex to fill
what remains of the 1-page budget. This prompt decides WHAT earns that flex
space for a specific JD:
- which skill items (from the profile inventory — never invented) to print,
- which projects earn a line, each with a 2–3 word descriptor, and whether
  the project's one-line description adds enough JD-relevant evidence to
  spend a second line on.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

PROMPT = """You are tailoring the SKILLS and PROJECTS sections of a dense 1-page resume
for one specific job. Work experience bullets are selected elsewhere and get
space priority; skills and projects flex to fill what remains.

Job:
Role: {role}
Description: {description}
Required skills: {skills_required}

Candidate's full skills inventory (category → items):
{skills_inventory}

Candidate's projects (id → title · tags · summary):
{projects_inventory}

Decide two things:

1. `skills` — the items to PRINT, per category, for THIS job.
   - Keep only items that support this JD: its named stack, plus closely
     adjacent foundations a reviewer would expect alongside it.
   - Copy item spellings EXACTLY from the inventory. Never invent, merge, or
     re-spell an item.
   - Order items within a category most-JD-relevant first.
   - Drop a whole category when nothing in it earns space.
   - Keep the category names exactly as given.

2. `projects` — which projects earn a line on the page.
   - `include: true` only when the project adds evidence the work experience
     doesn't already cover (a JD-relevant technology, domain, or proof of
     initiative). Most jobs warrant 1–3 projects; zero is fine.
   - `descriptor`: a 2–3 word plain-language tagline rendered right after the
     title, e.g. "career automation platform" or "distributed key-value store".
     No tech laundry lists, no marketing fluff.
   - `include_description: true` ONLY when the project's one-line summary adds
     JD-relevant evidence beyond title + descriptor. Default false — a tight
     one-line entry usually reads better on a packed page.

Return TailoredSections.
"""


class TailoredSkillGroup(BaseModel):
    category: str
    items: list[str] = Field(default_factory=list)


class TailoredProjectPick(BaseModel):
    id: int
    include: bool = True
    descriptor: str = ""
    include_description: bool = False


class TailoredSections(BaseModel):
    skills: list[TailoredSkillGroup] = Field(default_factory=list)
    projects: list[TailoredProjectPick] = Field(default_factory=list)
    rationale: str = ""
