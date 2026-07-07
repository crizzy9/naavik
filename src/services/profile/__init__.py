"""Profile package — profile/experience/bullet/education/project/skill CRUD,
resume-text extraction, portfolio sync, and stored application answers.

Plan 92 Phase B4 grouped the former flat modules `profile_service` /
`extraction` / `portfolio_sync` / `profile_answer_service` into this
package.

Seam tiers:

- Package surface (this `__init__`): the profile service API — the
  conftest shims land here and callers read `profile_service.get_profile(...)`
  through a `from services import profile as profile_service` alias, so
  `patch("services.profile.X")` intercepts.
- Module tier: `extraction`, `portfolio_sync` (patch as
  `services.profile.portfolio_sync.X`), and `answers` (the stored
  screener-answer service, formerly `profile_answer_service`).
"""

from __future__ import annotations

from services.profile.service import (
    ALLOWED_PROFILE_FIELDS,
    add_bullet,
    add_certification,
    add_education,
    add_experience,
    add_project,
    add_skill,
    delete_bullet,
    delete_certification,
    delete_education,
    delete_experience,
    delete_project,
    delete_skill,
    get_bullet,
    get_bullets_for_experience,
    get_experience,
    get_profile,
    get_score_history,
    list_all_bullets,
    list_certifications,
    list_educations,
    list_experiences,
    list_projects,
    list_skills,
    owns_bullet,
    owns_certification,
    owns_education,
    owns_experience,
    owns_project,
    owns_skill,
    parse_resume_heuristics,
    reorder_bullets,
    set_raw_resume_text,
    total_years_experience,
    update_application_questions,
    update_bullet,
    update_certification,
    update_education,
    update_experience,
    update_field,
    update_project,
    update_skill,
)

__all__ = [
    "ALLOWED_PROFILE_FIELDS",
    "add_bullet",
    "add_certification",
    "add_education",
    "add_experience",
    "add_project",
    "add_skill",
    "delete_bullet",
    "delete_certification",
    "delete_education",
    "delete_experience",
    "delete_project",
    "delete_skill",
    "get_bullet",
    "get_bullets_for_experience",
    "get_experience",
    "get_profile",
    "get_score_history",
    "list_all_bullets",
    "list_certifications",
    "list_educations",
    "list_experiences",
    "list_projects",
    "list_skills",
    "owns_bullet",
    "owns_certification",
    "owns_education",
    "owns_experience",
    "owns_project",
    "owns_skill",
    "parse_resume_heuristics",
    "reorder_bullets",
    "set_raw_resume_text",
    "total_years_experience",
    "update_application_questions",
    "update_bullet",
    "update_certification",
    "update_education",
    "update_experience",
    "update_field",
    "update_project",
    "update_skill",
]
