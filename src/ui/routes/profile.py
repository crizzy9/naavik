"""Profile + Profile editor HTML page handlers.

Wave 4 of plan 10 § B.7 moves the JSON `/api/v1/profile/*` and
`/api/v1/bullets/*` endpoints to `src/api/profile.py` (real DB-backed
handlers via `services/profile_service.py`). Plan 69 (0.3.3.12) rewires
the page-handler reads from the in-memory `sample_data` shim onto the
same service-layer surface.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from db.session import get_session
from models import User
from services import profile_service
from services.auth import require_authed_session
from ui import profile_ctx as pctx
from ui.templates_setup import templates

router = APIRouter()


def _effective_user_id(user: User | None) -> int:
    """Real JWT → user.id; fake-session transitional stub → seeded owner id=1."""
    return user.id if user is not None else 1


async def _build_profile_ctx(session: AsyncSession, user_id: int) -> dict[str, object]:
    profile = await profile_service.get_profile(session, user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    experiences = await profile_service.list_experiences(session, user_id)
    exp_view = []
    for e in experiences:
        bullets = await profile_service.get_bullets_for_experience(session, e.id)
        exp_view.append(
            {
                "model": e,
                "display": pctx.experience_dict(e),
                "bullets": [pctx.bullet_dict(b) for b in bullets],
            }
        )
    # Plan 73 (0.3.2.03): sparkline strip in the Profile hero.
    # `profile.score_history` is the JSONB column (default {}); `score_trend`
    # is the top-3 families projection consumed by `profile_hero.html`.
    score_history = await profile_service.get_score_history(session, user_id)
    all_projects = pctx.project_dicts(await profile_service.list_projects(session, user_id))
    return {
        "profile": profile,
        "hero": pctx.hero_dict(profile),
        "score_trend": pctx.score_trend_strip(score_history),
        "experiences": exp_view,
        "skills": pctx.skill_dicts(await profile_service.list_skills(session, user_id)),
        "educations": pctx.education_dicts(await profile_service.list_educations(session, user_id)),
        "projects": [p for p in all_projects if p["kind"] != "open_source"],
        "open_source": [p for p in all_projects if p["kind"] == "open_source"],
        "certifications": pctx.certification_dicts(
            await profile_service.list_certifications(session, user_id)
        ),
        "app_questions": pctx.app_questions_pairs(profile),
        "anchors": pctx.PROFILE_ANCHORS,
        "readiness": pctx.application_readiness(profile),
        # Job-search preferences editor (components/_search_prefs_editor.html)
        "sp": {
            "target_titles": list(getattr(profile, "target_titles", None) or []),
            "expansions": dict(getattr(profile, "title_expansions", None) or {}),
            "target_cities": list(getattr(profile, "target_cities", None) or []),
            "remote_ok": bool(getattr(profile, "remote_ok", True)),
        },
    }


@router.get("/profile", response_class=HTMLResponse, name="profile")
async def get_profile(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    ctx = await _build_profile_ctx(session, _effective_user_id(user))
    ctx["active_sidebar"] = "profile"
    ctx["active_template_path"] = "/profile"
    return templates.TemplateResponse(request, "pages/profile.html", ctx)


@router.get("/profile/edit", response_class=HTMLResponse, name="profile_edit")
async def get_edit(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    ctx = await _build_profile_ctx(session, _effective_user_id(user))
    ctx["active_sidebar"] = "profile"
    ctx["active_template_path"] = "/profile/edit"
    return templates.TemplateResponse(request, "pages/profile_edit.html", ctx)


@router.get("/_fragments/profile/cities", response_class=HTMLResponse, name="profile_cities")
async def get_city_suggestions(
    request: Request,
    q: str = "",
    _user: User | None = Depends(require_authed_session),
):
    """City-autocomplete suggestion list for the job-search prefs editor."""
    from services.geo import search_cities

    return templates.TemplateResponse(
        request,
        "components/_city_suggestions.html",
        {"items": search_cities(q) if len(q.strip()) >= 2 else []},
    )
