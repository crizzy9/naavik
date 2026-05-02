"""Profile + Profile editor HTML page handlers.

Wave 4 of plan 10 § B.7 moves the JSON `/api/v1/profile/*` and
`/api/v1/bullets/*` endpoints to `src/api/profile.py` (real DB-backed
handlers via `services/profile_service.py`).

What stays here:
- `GET /profile` and `GET /profile/edit` page handlers.
- A thin sample-data accessor pipeline so the page templates render the
  same context shape they always did.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from db import sample_data as sd
from ui import profile_ctx as pctx
from ui.templates_setup import templates

router = APIRouter()


async def _build_profile_ctx() -> dict[str, object]:
    profile = await sd.get_profile()
    experiences = await sd.get_experiences()
    bullets_by_exp = {e.id: await sd.get_bullets_for_experience(e.id) for e in experiences}
    exp_view = []
    for e in experiences:
        exp_view.append(
            {
                "model": e,
                "display": pctx.experience_dict(e),
                "bullets": [pctx.bullet_dict(b) for b in bullets_by_exp[e.id]],
            }
        )
    return {
        "profile": profile,
        "hero": pctx.hero_dict(profile),
        "experiences": exp_view,
        "skills": pctx.skill_dicts(await sd.get_skills()),
        "educations": pctx.education_dicts(await sd.get_educations()),
        "projects": pctx.project_dicts(await sd.get_projects()),
        "certifications": pctx.certification_dicts(await sd.get_certifications()),
        "app_questions": pctx.app_questions_pairs(profile),
        "anchors": pctx.PROFILE_ANCHORS,
        "readiness": pctx.application_readiness(profile),
    }


@router.get("/profile", response_class=HTMLResponse, name="profile")
async def get_profile(request: Request):
    ctx = await _build_profile_ctx()
    ctx["active_sidebar"] = "profile"
    ctx["active_template_path"] = "/profile"
    return templates.TemplateResponse(request, "pages/profile.html", ctx)


@router.get("/profile/edit", response_class=HTMLResponse, name="profile_edit")
async def get_edit(request: Request):
    ctx = await _build_profile_ctx()
    ctx["active_sidebar"] = "profile"
    ctx["active_template_path"] = "/profile/edit"
    return templates.TemplateResponse(request, "pages/profile_edit.html", ctx)
