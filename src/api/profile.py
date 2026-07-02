"""Real `/api/v1/profile/*` and `/api/v1/bullets/*` handlers.

Wave 4 of plan 10 § B.7. Replaces the plan-09 stubs in
`src/ui/routes/profile.py` for state-changing endpoints. Page handlers
(`GET /profile`, `GET /profile/edit`) stay in `src/ui/routes/profile.py`.

These mount under `/api/v1/profile` + `/api/v1/bullets`.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Form, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from api.auth import require_csrf
from db.session import get_session
from models import User
from services import profile_service
from services.auth import require_authed_session
from ui.routes.profile import _effective_user_id
from ui.templates_setup import templates

router = APIRouter()


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
        # Unknown names (e.g. `title_<id>`, `start_<id>`, `end_<id>` per-experience
        # editors) are intentionally ignored at the bulk endpoint — experience edits
        # have dedicated routes scoped by id; the bulk save covers Profile fields.

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


# ── Per-field PUT (legacy autosave — retained for non-profile-edit consumers) ──


@router.put("/api/v1/profile/{field}", name="api_profile_put_field")
async def put_field(
    request: Request,
    field: str,
    fail: Annotated[str | None, Query()] = None,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
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


@router.put("/api/v1/profile/application-questions", name="api_profile_put_application_questions")
async def put_application_questions(
    request: Request,
    payload: Annotated[dict[str, Any] | None, Body()] = None,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
):
    payload = payload or {}
    try:
        await profile_service.update_application_questions(
            session,
            user_id=_effective_user_id(_user),
            payload=payload,
        )
        await session.commit()
    except LookupError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


# ── Bullets ─────────────────────────────────────────────────────────────


@router.post("/api/v1/bullets", name="api_bullets_post")
async def post_bullet(
    request: Request,
    text: Annotated[str, Form()] = "",
    experience_id: Annotated[int, Form()] = 0,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
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
    fail: Annotated[str | None, Query()] = None,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
):
    if fail:
        raise HTTPException(status_code=422, detail="Couldn't save bullet")
    if not await profile_service.owns_bullet(
        session, bullet_id=bullet_id, user_id=_effective_user_id(_user)
    ):
        raise HTTPException(status_code=404, detail="Bullet not found")
    try:
        bullet = await profile_service.update_bullet(session, bullet_id, text=text)
        await session.commit()
    except LookupError as exc:
        await session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    response = _bullet_row_response(request, bullet)
    response.headers["HX-Trigger"] = "closeModal"
    return response


@router.delete("/api/v1/bullets/{bullet_id}", name="api_bullets_delete")
async def delete_bullet(
    bullet_id: int,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
):
    if not await profile_service.owns_bullet(
        session, bullet_id=bullet_id, user_id=_effective_user_id(_user)
    ):
        raise HTTPException(status_code=404, detail="Bullet not found")
    deleted = await profile_service.delete_bullet(session, bullet_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Bullet not found")
    await session.commit()
    response = Response(status_code=204)
    response.headers["HX-Trigger"] = "closeModal, bulletDeleted"
    return response


@router.post("/api/v1/bullets/{bullet_id}/rewrite", name="api_bullets_rewrite")
async def post_bullet_rewrite(
    bullet_id: int,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    """Rewrite a bullet with the configured LLM (tighten to one resume line,
    preserving numbers + verbs).

    Was a stub that appended a literal " (rewritten by AI)" — a fake-success
    state. Now calls the real provider via the `trim_bullet` prompt through
    `llm_tracker.tracked_call` (so ApiUsage is recorded). Returns a friendly
    422 when no LLM provider is configured instead of pretending it worked.
    The rewrite is NOT persisted — the client shows it as a suggested edit the
    user accepts via the normal bullet PUT.
    """
    from llm import get_provider
    from llm.base import LLMProviderError
    from llm.prompts.trim_bullet import PROMPT as TRIM_PROMPT
    from llm.prompts.trim_bullet import TrimmedBullet
    from services import llm_tracker, settings_service

    user_id = _effective_user_id(_user)
    if not await profile_service.owns_bullet(session, bullet_id=bullet_id, user_id=user_id):
        raise HTTPException(status_code=404, detail="Bullet not found")
    bullet = await profile_service.get_bullet(session, bullet_id)
    if bullet is None:
        raise HTTPException(status_code=404, detail="Bullet not found")

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

    rendered = TRIM_PROMPT.format(text=bullet.text, target_chars=160)
    try:
        result = await llm_tracker.tracked_call(
            session=session,
            user_id=user_id,
            provider=provider,
            method="structured",
            prompt_name="trim_bullet",
            prompt=rendered,
            schema=TrimmedBullet,
        )
        await session.commit()
    except LLMProviderError as exc:
        await session.rollback()
        raise HTTPException(status_code=502, detail=f"LLM rewrite failed: {exc}") from exc

    trimmed = TrimmedBullet.model_validate(result.value)
    return {
        "id": bullet.id,
        "text": trimmed.trimmed,
        "tags": list(bullet.tags or []),
        "edited": True,
    }


@router.post("/api/v1/bullets/reorder", name="api_bullets_reorder")
async def post_bullets_reorder(
    payload: Annotated[dict[str, Any] | None, Body()] = None,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
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
