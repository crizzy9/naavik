"""Real `/api/v1/profile/*` and `/api/v1/bullets/*` handlers.

Wave 4 of plan 10 § B.7. Replaces the plan-09 stubs in
`src/ui/routes/profile.py` for state-changing endpoints. Page handlers
(`GET /profile`, `GET /profile/edit`) stay in `src/ui/routes/profile.py`.

These mount under `/api/v1/profile` + `/api/v1/bullets`.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Form, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from api.auth import require_csrf
from db.session import get_session
from models import User
from models.enums import BulletSelectionOverride
from services import profile as profile_service
from services.auth import require_authed_session
from ui.routes.profile import _effective_user_id
from ui.templates_setup import TAG_VOCAB, templates

router = APIRouter()


# ── Dossier entity form-field parsing (item 1, 2026-07) ─────────────────
# The profile editor posts per-entity fields as `<prefix>_<field>_<id>`
# (e.g. `exp_company_12`, `edu_gpa_3`). The bulk PUT collects them per
# entity row and routes through the profile_service CRUD with ownership
# checks. Dates arrive as `YYYY-MM-DD` (or empty).

_ENTITY_FIELD_RE = re.compile(
    r"^(exp|edu|proj|oss|skill|cert)_"
    r"(company|title|team|location|start|end|institution|school|degree|gpa|"
    r"date|text|link|tags|category|items|issuer|description|selection_override)_(\d+)$"
)

_DATE_FIELDS = {"start", "end", "date"}
_CSV_FIELDS = {"tags", "items"}


def _parse_form_date(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    raise ValueError(f"bad date {value!r} — expected YYYY-MM-DD")


def _collect_entity_edits(form_items) -> dict[tuple[str, int], dict[str, Any]]:
    """Group `<prefix>_<field>_<id>` form fields into per-entity dicts."""
    edits: dict[tuple[str, int], dict[str, Any]] = {}
    for name, value in form_items:
        m = _ENTITY_FIELD_RE.match(name)
        if m is None:
            continue
        prefix, field, entity_id = m.group(1), m.group(2), int(m.group(3))
        raw = str(value)
        parsed: Any
        entity = edits.setdefault((prefix, entity_id), {})
        if field in _DATE_FIELDS:
            parsed = _parse_form_date(raw)  # raises ValueError — caller collects
        elif field in _CSV_FIELDS:
            # Chip editors submit one input PER value under the same name
            # (plus an empty sentinel so "no chips" still clears the field);
            # legacy single CSV inputs keep working via the split. Repeated
            # keys ACCUMULATE instead of last-one-wins.
            parsed = [t.strip() for t in raw.split(",") if t.strip()]
            existing = entity.get(field)
            if isinstance(existing, list):
                parsed = existing + [t for t in parsed if t not in existing]
        else:
            parsed = raw
        entity[field] = parsed
    return edits


def _parse_override(raw: Any) -> BulletSelectionOverride | None:
    """Empty string (the select's "AI decides" option) clears back to null."""
    value = str(raw or "").strip()
    if not value:
        return None
    return BulletSelectionOverride(value)  # ValueError bubbles → caller's 400


async def _apply_entity_edit(
    session: AsyncSession,
    *,
    user_id: int,
    prefix: str,
    entity_id: int,
    fields: dict[str, Any],
) -> None:
    """Route one entity's field dict through the service layer (IDOR-guarded)."""
    if prefix == "exp":
        if not await profile_service.owns_experience(
            session, experience_id=entity_id, user_id=user_id
        ):
            raise LookupError("experience not found")
        await profile_service.update_experience(
            session,
            entity_id,
            company=fields.get("company"),
            title=fields.get("title"),
            team=fields.get("team"),
            location=fields.get("location"),
            start_date=fields.get("start"),
            end_date=fields.get("end", "__unset__"),
        )
    elif prefix == "edu":
        if not await profile_service.owns_education(
            session, education_id=entity_id, user_id=user_id
        ):
            raise LookupError("education not found")
        await profile_service.update_education(
            session,
            entity_id,
            institution=fields.get("institution"),
            school=fields.get("school"),
            location=fields.get("location"),
            degree=fields.get("degree"),
            gpa=fields.get("gpa"),
            **({"start_date": fields["start"]} if fields.get("start") else {}),
            **({"end_date": fields["end"]} if "end" in fields else {}),
        )
    elif prefix in ("proj", "oss"):
        if not await profile_service.owns_project(session, project_id=entity_id, user_id=user_id):
            raise LookupError("project not found")
        # Same gate as put_bullet: project tags are vocab chips now, and the
        # job scorer depends on the 9-tag vocabulary — drop anything else.
        tags = fields.get("tags")
        if tags is not None:
            tags = [t for t in tags if t in TAG_VOCAB]
        await profile_service.update_project(
            session,
            entity_id,
            title=fields.get("title"),
            text=fields.get("text"),
            link=fields.get("link"),
            tags=tags,
            **({"date": fields["date"]} if "date" in fields else {}),
            **(
                {"selection_override": _parse_override(fields["selection_override"])}
                if "selection_override" in fields
                else {}
            ),
        )
    elif prefix == "skill":
        if not await profile_service.owns_skill(session, skill_id=entity_id, user_id=user_id):
            raise LookupError("skill group not found")
        await profile_service.update_skill(
            session,
            entity_id,
            category=fields.get("category"),
            items=fields.get("items"),
        )
    elif prefix == "cert":
        if not await profile_service.owns_certification(
            session, certification_id=entity_id, user_id=user_id
        ):
            raise LookupError("certification not found")
        await profile_service.update_certification(
            session,
            entity_id,
            title=fields.get("title"),
            issuer=fields.get("issuer"),
            description=fields.get("description"),
            **({"date": fields["date"]} if "date" in fields else {}),
            **(
                {"selection_override": _parse_override(fields["selection_override"])}
                if "selection_override" in fields
                else {}
            ),
        )


# ── Bulk PUT (Save changes) ─────────────────────────────────────────────


@router.put("/api/v1/profile", name="api_profile_put_bulk")
async def put_profile_bulk(
    request: Request,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
) -> HTMLResponse:
    """Bulk save the profile editor form.

    Walks the posted FormData, routes each field through the appropriate
    service (`update_field` for identity / summary / etc., `update_application_questions`
    for the EEO bag), and returns an HTML fragment swapped into
    `#profile-edit-save-result` on the edit page (0.7.0.48 fold-in for owner
    bug #4 — replaces the misleading static autosave indicator with an
    explicit Save button).
    """
    form = await request.form()
    eeo_fields = {
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
    eeo_payload: dict[str, Any] = {}
    saved_fields: list[str] = []
    failed: list[tuple[str, str]] = []
    user_id = _effective_user_id(_user)

    for name, value in form.multi_items():
        if name in eeo_fields:
            # Empty form values → NULL. Several EEO columns are typed
            # INTEGER / ENUM (notice_period_days, salary_expectation_usd,
            # work_authorization, visa_sponsorship_needed, …); asyncpg
            # raises `DataError: 'str' object cannot be interpreted as an
            # integer` if `''` reaches the encoder. Coerce at the boundary
            # so the operator can save a profile with EEO fields blank.
            # (Plan 0.7.0.48 W4 fix — owner-reported 500 on profile save.)
            eeo_payload[name] = value if value != "" else None
            continue
        if name in profile_service.ALLOWED_PROFILE_FIELDS:
            try:
                await profile_service.update_field(
                    session,
                    user_id=user_id,
                    field=name,
                    value=value,
                )
                saved_fields.append(name)
            except (LookupError, ValueError) as exc:
                failed.append((name, str(exc)))

    # Per-entity dossier fields (`exp_company_<id>`, `edu_gpa_<id>`, …) —
    # collected as one dict per entity row, then routed through the service
    # CRUD with ownership checks.
    try:
        entity_edits = _collect_entity_edits(form.multi_items())
    except ValueError as exc:
        entity_edits = {}
        failed.append(("dates", str(exc)))
    for (prefix, entity_id), fields in entity_edits.items():
        try:
            await _apply_entity_edit(
                session, user_id=user_id, prefix=prefix, entity_id=entity_id, fields=fields
            )
            saved_fields.append(f"{prefix}:{entity_id}")
        except (LookupError, ValueError) as exc:
            failed.append((f"{prefix}:{entity_id}", str(exc)))

    if eeo_payload:
        try:
            await profile_service.update_application_questions(
                session,
                user_id=user_id,
                payload=eeo_payload,
            )
            saved_fields.extend(sorted(eeo_payload.keys()))
        except LookupError as exc:
            failed.append(("application_questions", str(exc)))

    if failed:
        await session.rollback()
        msg = "; ".join(f"{name}: {err}" for name, err in failed)
        return HTMLResponse(
            f'<span class="text-rose-300">Save failed — {msg}</span>',
            status_code=422,
        )

    await session.commit()
    return HTMLResponse(
        f'<span class="text-emerald-300">Saved · {len(saved_fields)} field'
        f"{'s' if len(saved_fields) != 1 else ''}</span>"
    )


# ── Job-search preferences (docs/design/JOB_SEARCH_PREFERENCES.md § C) ──
# NOTE: registered BEFORE the `/{field}` catch-all so the literal path wins.


def _search_prefs_ctx(profile) -> dict[str, Any]:
    return {
        "sp": {
            "target_titles": list(getattr(profile, "target_titles", None) or []),
            "expansions": dict(getattr(profile, "title_expansions", None) or {}),
            "target_cities": list(getattr(profile, "target_cities", None) or []),
            "remote_ok": bool(getattr(profile, "remote_ok", True)),
        }
    }


@router.put("/api/v1/profile/search-prefs", name="api_profile_search_prefs")
async def put_search_prefs(
    request: Request,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
) -> HTMLResponse:
    """Mutate one aspect of the job-search preferences, re-render the editor.

    Actions (form-encoded): add_title / remove_title (title=), add_city /
    remove_city (city=), set_remote (remote_ok checkbox present = on).
    Title changes synchronously refresh the LLM expansion set (visible via
    the fragment's hx-indicator; degrades to exact-match with no provider).
    The response is the SAME `_search_prefs_editor.html` fragment the
    controls target — granularity matched to `closest [data-search-prefs]`.
    """
    from services import search_prefs, settings_service

    form = await request.form()
    action = str(form.get("action") or "")
    user_id = _effective_user_id(_user)
    profile = await profile_service.get_profile(session, user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="profile not found")

    titles_changed = False
    if action == "add_title":
        title = str(form.get("title") or "").strip()
        if title and title.lower() not in {t.lower() for t in profile.target_titles or []}:
            profile.target_titles = [*(profile.target_titles or []), title]
            titles_changed = True
    elif action == "remove_title":
        title = str(form.get("title") or "").strip()
        profile.target_titles = [
            t for t in (profile.target_titles or []) if t.lower() != title.lower()
        ]
        titles_changed = True
    elif action == "add_city":
        city = str(form.get("city") or "").strip()
        from services.geo import normalize_city

        normalized = normalize_city(city)
        if normalized and normalized not in (profile.target_cities or []):
            profile.target_cities = [*(profile.target_cities or []), normalized]
    elif action == "remove_city":
        city = str(form.get("city") or "").strip()
        profile.target_cities = [c for c in (profile.target_cities or []) if c != city]
    elif action == "set_remote":
        # Unchecked checkboxes are absent from the form payload.
        profile.remote_ok = form.get("remote_ok") is not None
    else:
        raise HTTPException(status_code=422, detail=f"unknown action {action!r}")

    session.add(profile)
    await session.flush()

    if titles_changed:
        user_settings = await settings_service.get_or_create(session, user_id=user_id)
        await search_prefs.refresh_title_expansions(
            session, profile=profile, settings=user_settings
        )

    await session.commit()
    return templates.TemplateResponse(
        request,
        "components/_search_prefs_editor.html",
        _search_prefs_ctx(profile),
    )


# ── Dossier entity add/remove (item 1, 2026-07) ─────────────────────────
# Add buttons hx-post here and append the returned editor-card fragment to
# the section list — the parent #profile-edit-form picks the new fields up
# on the next Save without losing unsaved edits elsewhere. Deletes return
# 204 + a `removeElement` HX-Trigger handled in base.js.


def _remove_element_response(selector: str, toast: str) -> Response:
    response = Response(status_code=204)
    response.headers["HX-Trigger"] = json.dumps(
        {
            "removeElement": {"selector": selector},
            "showToast": {"tone": "success", "text": toast},
            "closeModal": True,
        }
    )
    return response


@router.post("/api/v1/experiences", name="api_experiences_post")
async def post_experience(
    request: Request,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
) -> HTMLResponse:
    from ui import profile_ctx as pctx

    exp = await profile_service.add_experience(session, _effective_user_id(_user))
    await session.commit()
    return templates.TemplateResponse(
        request,
        "components/experience_edit_card.html",
        {"exp": {"model": exp, "display": pctx.experience_dict(exp), "bullets": []}},
    )


@router.delete("/api/v1/experiences/{experience_id}", name="api_experiences_delete")
async def delete_experience(
    experience_id: int,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
) -> Response:
    if not await profile_service.owns_experience(
        session, experience_id=experience_id, user_id=_effective_user_id(_user)
    ):
        raise HTTPException(status_code=404, detail="Experience not found")
    await profile_service.delete_experience(session, experience_id)
    await session.commit()
    return _remove_element_response(f"#experience-{experience_id}", "Role removed.")


@router.post("/api/v1/educations", name="api_educations_post")
async def post_education(
    request: Request,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
) -> HTMLResponse:
    from ui import profile_ctx as pctx

    edu = await profile_service.add_education(session, _effective_user_id(_user))
    await session.commit()
    return templates.TemplateResponse(
        request,
        "components/education_edit_card.html",
        {"edu": pctx.education_dicts([edu])[0]},
    )


@router.delete("/api/v1/educations/{education_id}", name="api_educations_delete")
async def delete_education(
    education_id: int,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
) -> Response:
    if not await profile_service.owns_education(
        session, education_id=education_id, user_id=_effective_user_id(_user)
    ):
        raise HTTPException(status_code=404, detail="Education not found")
    await profile_service.delete_education(session, education_id)
    await session.commit()
    return _remove_element_response(f"#education-{education_id}", "Education removed.")


@router.post("/api/v1/projects", name="api_projects_post")
async def post_project(
    request: Request,
    kind: Annotated[str, Form()] = "project",
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
) -> HTMLResponse:
    from ui import profile_ctx as pctx

    try:
        proj = await profile_service.add_project(session, _effective_user_id(_user), kind=kind)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await session.commit()
    return templates.TemplateResponse(
        request,
        "components/project_edit_card.html",
        {"proj": pctx.project_dicts([proj])[0]},
    )


@router.delete("/api/v1/projects/{project_id}", name="api_projects_delete")
async def delete_project(
    project_id: int,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
) -> Response:
    if not await profile_service.owns_project(
        session, project_id=project_id, user_id=_effective_user_id(_user)
    ):
        raise HTTPException(status_code=404, detail="Project not found")
    await profile_service.delete_project(session, project_id)
    await session.commit()
    return _remove_element_response(f"#project-{project_id}", "Removed.")


@router.post("/api/v1/skills", name="api_skills_post")
async def post_skill(
    request: Request,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
) -> HTMLResponse:
    from ui import profile_ctx as pctx

    skill = await profile_service.add_skill(session, _effective_user_id(_user))
    await session.commit()
    return templates.TemplateResponse(
        request,
        "components/skill_edit_card.html",
        {"skill": pctx.skill_dicts([skill])[0]},
    )


@router.delete("/api/v1/skills/{skill_id}", name="api_skills_delete")
async def delete_skill(
    skill_id: int,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
) -> Response:
    if not await profile_service.owns_skill(
        session, skill_id=skill_id, user_id=_effective_user_id(_user)
    ):
        raise HTTPException(status_code=404, detail="Skill group not found")
    await profile_service.delete_skill(session, skill_id)
    await session.commit()
    return _remove_element_response(f"#skill-{skill_id}", "Skill group removed.")


@router.post("/api/v1/certifications", name="api_certifications_post")
async def post_certification(
    request: Request,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
) -> HTMLResponse:
    from ui import profile_ctx as pctx

    cert = await profile_service.add_certification(session, _effective_user_id(_user))
    await session.commit()
    return templates.TemplateResponse(
        request,
        "components/certification_edit_card.html",
        {"cert": pctx.certification_dicts([cert])[0]},
    )


@router.delete("/api/v1/certifications/{certification_id}", name="api_certifications_delete")
async def delete_certification(
    certification_id: int,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
) -> Response:
    if not await profile_service.owns_certification(
        session, certification_id=certification_id, user_id=_effective_user_id(_user)
    ):
        raise HTTPException(status_code=404, detail="Certification not found")
    await profile_service.delete_certification(session, certification_id)
    await session.commit()
    return _remove_element_response(f"#certification-{certification_id}", "Certification removed.")


# ── Per-field PUT (legacy autosave — retained for non-profile-edit consumers) ──


@router.put("/api/v1/profile/{field}", name="api_profile_put_field")
async def put_field(
    request: Request,
    field: str,
    fail: Annotated[str | None, Query()] = None,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    """Per-field autosave. Returns the OOB autosave indicator partial."""
    if fail:
        return templates.TemplateResponse(
            request,
            "components/autosave_indicator.html",
            {"state": "error", "error_message": "Couldn't save — retry"},
            status_code=422,
        )
    if field not in profile_service.ALLOWED_PROFILE_FIELDS:
        raise HTTPException(status_code=404, detail="Unknown field")

    # Read raw form value — accept any string; service-layer coerces.
    form = await request.form()
    raw_value = form.get("value")

    try:
        await profile_service.update_field(
            session,
            user_id=_effective_user_id(_user),
            field=field,
            value=raw_value,
        )
        await session.commit()
    except (LookupError, ValueError) as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return templates.TemplateResponse(
        request,
        "components/autosave_indicator.html",
        {"state": "saved", "relative_time": "just now"},
    )


# NOTE: a PUT /api/v1/profile/application-questions route used to live here,
# but the `{field}` catch-all above is registered first and matches the path,
# so it was unreachable (plan 91 2.6). EEO-bag updates flow through the bulk
# PUT /api/v1/profile, which calls the same
# `profile_service.update_application_questions`.


# ── Bullets ─────────────────────────────────────────────────────────────


@router.post("/api/v1/bullets", name="api_bullets_post")
async def post_bullet(
    request: Request,
    text: Annotated[str, Form()] = "",
    experience_id: Annotated[int, Form()] = 0,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    if not experience_id:
        raise HTTPException(status_code=422, detail="experience_id is required")
    user_id = _effective_user_id(_user)
    if not await profile_service.owns_experience(
        session, experience_id=experience_id, user_id=user_id
    ):
        # 404 (not 403) to avoid leaking existence of other users' experiences.
        raise HTTPException(status_code=404, detail="Experience not found")
    bullet = await profile_service.add_bullet(
        session,
        experience_id=experience_id,
        text=text,
        tags=["backend"],
    )
    await session.commit()
    return _bullet_row_response(request, bullet)


@router.put("/api/v1/bullets/{bullet_id}", name="api_bullets_put")
async def put_bullet(
    request: Request,
    bullet_id: int,
    text: Annotated[str | None, Form()] = None,
    tags: Annotated[list[str] | None, Form(alias="tags[]")] = None,
    selection_override: Annotated[str | None, Form()] = None,
    editor_form: Annotated[str | None, Form()] = None,
    fail: Annotated[str | None, Query()] = None,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    if fail:
        raise HTTPException(status_code=422, detail="Couldn't save bullet")
    if not await profile_service.owns_bullet(
        session, bullet_id=bullet_id, user_id=_effective_user_id(_user)
    ):
        raise HTTPException(status_code=404, detail="Bullet not found")
    override: BulletSelectionOverride | None = None
    if selection_override:
        try:
            override = BulletSelectionOverride(selection_override)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Unknown selection_override") from exc
    # The bullet-editor modal submits the whole form (`editor_form=1`), where
    # unchecked tag checkboxes / cleared override radios are simply ABSENT —
    # absence there means "cleared", not "leave unchanged". Partial (legacy)
    # PUTs keep patch semantics: only provided fields change.
    if editor_form:
        tags = [t for t in (tags or []) if t in TAG_VOCAB]
        kwargs: dict = {"text": text, "tags": tags, "selection_override": override}
    else:
        kwargs = {"text": text}
        if tags is not None:
            kwargs["tags"] = [t for t in tags if t in TAG_VOCAB]
        if override is not None:
            kwargs["selection_override"] = override
    try:
        bullet = await profile_service.update_bullet(session, bullet_id, **kwargs)
        await session.commit()
    except LookupError as exc:
        await session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    response = _bullet_row_response(request, bullet)
    response.headers["HX-Trigger"] = json.dumps(
        {"closeModal": True, "showToast": {"tone": "success", "text": "Bullet saved."}}
    )
    return response


@router.delete("/api/v1/bullets/{bullet_id}", name="api_bullets_delete")
async def delete_bullet(
    bullet_id: int,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    if not await profile_service.owns_bullet(
        session, bullet_id=bullet_id, user_id=_effective_user_id(_user)
    ):
        raise HTTPException(status_code=404, detail="Bullet not found")
    deleted = await profile_service.delete_bullet(session, bullet_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Bullet not found")
    await session.commit()
    # Same pattern as the other dossier deletes: without `removeElement` the
    # soft-deleted row stayed on screen until reload ("delete did nothing").
    # Bullet rows carry data-bullet-id, not an id attribute.
    return _remove_element_response(f'[data-bullet-id="{bullet_id}"]', "Bullet deleted.")


@router.post("/api/v1/bullets/{bullet_id}/rewrite", name="api_bullets_rewrite")
async def post_bullet_rewrite(
    request: Request,
    bullet_id: int,
    text: Annotated[str | None, Form()] = None,
    rewrite_style: Annotated[str | None, Form()] = None,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    """Style-directed rewrite: 2-3 variants + a one-line model note.

    The old wiring used trim_bullet@160 chars, so any already-short bullet
    came back byte-identical ("Rewrite did nothing"). Now the modal submits
    a `rewrite_style` chip and the CURRENT textarea text (so unsaved edits
    are rewritten, not the stored row), and gets back clickable variant
    cards (`components/bullet_rewrite_results.html`). Picking a card fills
    the textarea client-side; nothing persists until the normal Save PUT.
    Friendly 422 when no provider is configured.
    """
    from llm import get_provider
    from llm.base import LLMProviderError
    from llm.prompts.rewrite_bullet import DEFAULT_STYLE, PROMPT, STYLES, BulletRewrite
    from services import llm_tracker, settings_service

    user_id = _effective_user_id(_user)
    if not await profile_service.owns_bullet(session, bullet_id=bullet_id, user_id=user_id):
        raise HTTPException(status_code=404, detail="Bullet not found")
    bullet = await profile_service.get_bullet(session, bullet_id)
    if bullet is None:
        raise HTTPException(status_code=404, detail="Bullet not found")

    style = rewrite_style if rewrite_style in STYLES else DEFAULT_STYLE
    source_text = (text or "").strip() or bullet.text
    if not source_text.strip():
        raise HTTPException(status_code=422, detail="Nothing to rewrite — the bullet is empty.")

    s = await settings_service.get_or_create(session, user_id=user_id)
    try:
        provider = get_provider(s)
    except Exception as exc:  # noqa: BLE001 — surface config gaps as 422, not 500
        raise HTTPException(
            status_code=422,
            detail=(
                "No LLM provider configured. Set an API key (ANTHROPIC_API_KEY / "
                "OPENAI_API_KEY) or OLLAMA_BASE_URL in .env and restart to enable "
                "AI rewrite."
            ),
        ) from exc

    rendered = PROMPT.format(
        style=style, style_guidance=STYLES[style], text=source_text, target_chars=160
    )
    try:
        result = await llm_tracker.tracked_call(
            session=session,
            user_id=user_id,
            provider=provider,
            method="structured",
            prompt_name="rewrite_bullet",
            prompt=rendered,
            schema=BulletRewrite,
        )
        await session.commit()
    except LLMProviderError as exc:
        await session.rollback()
        raise HTTPException(status_code=502, detail=f"LLM rewrite failed: {exc}") from exc

    rewrite = BulletRewrite.model_validate(result.value)
    variants = [v.strip() for v in rewrite.variants if v and v.strip()][:3]
    if not variants:
        raise HTTPException(
            status_code=502, detail="The model returned no usable variants — try again."
        )
    response = templates.TemplateResponse(
        request,
        "components/bullet_rewrite_results.html",
        {"variants": variants, "note": rewrite.note.strip(), "style": style},
    )
    response.headers["HX-Trigger"] = json.dumps(
        {"showToast": {"tone": "info", "text": "Variants ready — click one, review, then Save."}}
    )
    return response


@router.post("/api/v1/bullets/reorder", name="api_bullets_reorder")
async def post_bullets_reorder(
    payload: Annotated[dict[str, Any] | None, Body()] = None,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    payload = payload or {}
    bullet_ids = payload.get("bullet_ids") or []
    experience_id = payload.get("experience_id")
    # Best-effort across-experience reorder if `experience_id` is omitted —
    # plan-09 was loose about this.
    if not experience_id:
        # Need experience_id to scope; fall back to no-op.
        return Response(status_code=204)
    if not await profile_service.owns_experience(
        session, experience_id=int(experience_id), user_id=_effective_user_id(_user)
    ):
        raise HTTPException(status_code=404, detail="Experience not found")
    try:
        ids = [int(bid) for bid in bullet_ids]
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="bullet_ids must be ints") from exc
    await profile_service.reorder_bullets(
        session,
        experience_id=int(experience_id),
        bullet_ids=ids,
    )
    await session.commit()
    return Response(status_code=204)


# ── Helpers ──────────────────────────────────────────────────────────────


def _bullet_row_response(request: Request, bullet) -> HTMLResponse:
    """Render the bullet_edit_row partial — same shape plan 09 produced."""
    return templates.TemplateResponse(
        request,
        "components/bullet_edit_row.html",
        {
            "bullet": {
                "id": bullet.id,
                "experience_id": bullet.experience_id,
                "text": bullet.text,
                "tags": list(bullet.tags or []),
                "selection_override": (
                    bullet.selection_override.value if bullet.selection_override else None
                ),
                "edited": True,
                "edited_at_display": "just now",
            },
        },
    )
