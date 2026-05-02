"""Profile + Profile editor routes + bullet / field-autosave stubs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Body, Form, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse

from db import sample_data as sd
from ui import profile_ctx as pctx
from ui.templates_setup import templates

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────
# Page handlers
# ─────────────────────────────────────────────────────────────────────────


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


# ─────────────────────────────────────────────────────────────────────────
# Profile field autosave + application questions (BACKEND.md § D.2)
# ─────────────────────────────────────────────────────────────────────────


_ALLOWED_FIELDS = {
    "full_name",
    "headline",
    "current_company",
    "location",
    "email",
    "phone",
    "portfolio_url",
    "github_handle",
    "linkedin_handle",
    "summary_full",
    "summary_short",
    "work_authorization",
    "visa_sponsorship_needed",
    "willing_to_relocate",
    "notice_period_days",
    "salary_expectation_usd",
    "earliest_start",
    "veteran_status",
    "disability_status",
    "race_ethnicity",
    "gender_identity",
}


@router.put("/api/v1/profile/{field}", name="profile_put_field")
async def put_field(
    request: Request,
    field: str,
    fail: Annotated[str | None, Query()] = None,
):
    if field not in _ALLOWED_FIELDS:
        raise HTTPException(status_code=404, detail="Unknown field")
    if fail:
        return templates.TemplateResponse(
            request,
            "components/autosave_indicator.html",
            {"state": "error", "error_message": "Couldn't save — retry"},
            status_code=422,
        )
    return templates.TemplateResponse(
        request,
        "components/autosave_indicator.html",
        {"state": "saved", "relative_time": "just now"},
    )


@router.put("/api/v1/profile/application-questions", name="profile_put_application_questions")
async def put_application_questions(request: Request):
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────────────
# Bullets (BACKEND.md § D.2)
# ─────────────────────────────────────────────────────────────────────────


@router.post("/api/v1/bullets", name="bullets_post")
async def post_bullet(
    request: Request,
    text: Annotated[str, Form()] = "",
    experience_id: Annotated[int, Form()] = 0,
):
    """Stub — append a placeholder bullet (in-memory) and return the row."""
    from db.sample_data_models import Bullet
    from models.enums import Tag

    new_id = sd._next_id(sd.BULLETS)  # type: ignore[attr-defined]
    now = datetime.now(UTC)
    b = Bullet(
        id=new_id,
        experience_id=experience_id or 1,
        order_index=999,
        text=text or "New bullet — edit to write the long version.",
        tags=[Tag.BACKEND],
        selection_override=None,
        edited_at=now,
        created_at=now,
        updated_at=now,
    )
    sd.BULLETS.append(b)
    return templates.TemplateResponse(
        request,
        "components/bullet_edit_row.html",
        {"bullet": pctx.bullet_dict(b)},
    )


@router.put("/api/v1/bullets/{bullet_id}", name="bullets_put")
async def put_bullet(
    request: Request,
    bullet_id: int,
    text: Annotated[str | None, Form()] = None,
    fail: Annotated[str | None, Query()] = None,
):
    if fail:
        raise HTTPException(status_code=422, detail="Couldn't save bullet")
    b = await sd.get_bullet(bullet_id)
    if b is None:
        raise HTTPException(status_code=404, detail="Bullet not found")
    if text is not None:
        b.text = text
    b.edited_at = datetime.now(UTC)
    b.updated_at = datetime.now(UTC)
    response = templates.TemplateResponse(
        request,
        "components/bullet_edit_row.html",
        {"bullet": pctx.bullet_dict(b)},
    )
    response.headers["HX-Trigger"] = "closeModal"
    return response


@router.delete("/api/v1/bullets/{bullet_id}", name="bullets_delete")
async def delete_bullet(bullet_id: int):
    b = await sd.get_bullet(bullet_id)
    if b is None:
        raise HTTPException(status_code=404, detail="Bullet not found")
    b.deleted_at = datetime.now(UTC)
    if b in sd.BULLETS:
        sd.BULLETS.remove(b)
    response = Response(status_code=204)
    response.headers["HX-Trigger"] = "closeModal, bulletDeleted"
    return response


@router.post("/api/v1/bullets/{bullet_id}/rewrite", name="bullets_rewrite")
async def post_bullet_rewrite(request: Request, bullet_id: int):
    """Stub LLM rewrite — return the bullet text marked `edited`."""
    b = await sd.get_bullet(bullet_id)
    if b is None:
        raise HTTPException(status_code=404, detail="Bullet not found")
    return {
        "id": b.id,
        "text": b.text + " (rewritten by AI)",
        "tags": [t.value for t in b.tags],
        "edited": True,
    }


@router.post("/api/v1/bullets/reorder", name="bullets_reorder")
async def post_bullets_reorder(payload: Annotated[dict[str, Any] | None, Body()] = None):
    """Accept `{bullet_ids: [...]}` and apply to in-memory order_index."""
    if payload and isinstance(payload.get("bullet_ids"), list):
        for idx, bid in enumerate(payload["bullet_ids"]):
            try:
                bid_int = int(bid)
            except (TypeError, ValueError):
                continue
            for b in sd.BULLETS:
                if b.id == bid_int:
                    b.order_index = idx
    return Response(status_code=204)
