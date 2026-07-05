"""Tracking route + fragment + JSON stubs."""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession

from api.auth import require_csrf
from config import settings as app_settings
from db.session import get_session
from models import User
from models.enums import AppEventKind, ApplicationStatus, ClosedReason, JobQueueState
from services import application_analytics, applications
from services.auth import require_authed_session
from ui import tracking_ctx as tctx
from ui.templates_setup import templates

# Mirrors `api.applications._POSTMORTEM_TS_RE` (plan 52). Strict UTC-stamp
# regex blocks path-traversal payloads at the routing layer.
_POSTMORTEM_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z$")

router = APIRouter()


def _effective_user_id(user: User | None) -> int:
    return user.id if user is not None else 1


# ─────────────────────────────────────────────────────────────────────────
# Page handler
# ─────────────────────────────────────────────────────────────────────────


@router.get("/tracking", response_class=HTMLResponse, name="tracking")
async def get_tracking(
    request: Request,
    view: Annotated[Literal["board", "list"], Query()] = "board",
    tab: Annotated[Literal["pipeline", "library"], Query()] = "pipeline",
    state: Annotated[str, Query()] = "all",
    q: Annotated[str, Query()] = "",
    score_min: Annotated[float, Query()] = 0.0,
    show_closed: Annotated[int, Query()] = 0,
    show_drafts: Annotated[int, Query()] = 0,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    user_id = _effective_user_id(user)
    ctx = await tctx.build_tracking_ctx(
        session,
        user_id=user_id,
        view=view,
        show_closed=bool(show_closed),
        show_drafts=bool(show_drafts),
    )
    ctx["current_tab"] = tab
    if tab == "library":
        ctx.update(
            await tctx.build_library_ctx(
                session, user_id=user_id, state=state, q=q, score_min=score_min
            )
        )
    ctx["active_sidebar"] = "tracking"
    ctx["active_template_path"] = "/tracking"
    return templates.TemplateResponse(request, "pages/tracking.html", ctx)


# ─────────────────────────────────────────────────────────────────────────
# Fragment endpoints
# ─────────────────────────────────────────────────────────────────────────


@router.get(
    "/_fragments/tracking/board", response_class=HTMLResponse, name="tracking_board_fragment"
)
async def fragment_board(
    request: Request,
    show_closed: Annotated[int, Query()] = 0,
    show_drafts: Annotated[int, Query()] = 0,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    ctx = await tctx.build_tracking_ctx(
        session,
        user_id=_effective_user_id(user),
        view="board",
        show_closed=bool(show_closed),
        show_drafts=bool(show_drafts),
    )
    return templates.TemplateResponse(request, "pages/_tracking_board.html", ctx)


@router.get("/_fragments/tracking/list", response_class=HTMLResponse, name="tracking_list_fragment")
async def fragment_list(
    request: Request,
    show_closed: Annotated[int, Query()] = 1,
    show_drafts: Annotated[int, Query()] = 0,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    # Honor the caller's `show_closed` param (defaults to 1 — the list view
    # historically showed everything). Previously this was hardcoded to True,
    # so the list view ignored the toggle entirely.
    ctx = await tctx.build_tracking_ctx(
        session,
        user_id=_effective_user_id(user),
        view="list",
        show_closed=bool(show_closed),
        show_drafts=bool(show_drafts),
    )
    return templates.TemplateResponse(request, "pages/_tracking_list.html", ctx)


@router.get(
    "/_fragments/tracking/library",
    response_class=HTMLResponse,
    name="tracking_library_fragment",
)
async def fragment_library(
    request: Request,
    state: Annotated[str, Query()] = "all",
    q: Annotated[str, Query()] = "",
    score_min: Annotated[float, Query()] = 0.0,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    """Jobs-library fragment — facet chips + search re-render the table."""
    ctx = await tctx.build_library_ctx(
        session,
        user_id=_effective_user_id(user),
        state=state,
        q=q,
        score_min=score_min,
    )
    return templates.TemplateResponse(request, "pages/_tracking_library.html", ctx)


_LIBRARY_ACTIONS: dict[str, tuple[JobQueueState, str]] = {
    "save": (JobQueueState.SAVED, "Saved."),
    "skip": (JobQueueState.SKIPPED, "Skipped."),
    "restore": (JobQueueState.UNSWIPED, "Back in the review queue."),
    "queue": (JobQueueState.QUEUED_FOR_AUTO_APPLY, "Queued for auto-apply."),
}


@router.post(
    "/_fragments/tracking/library/{job_id}/{action}",
    response_class=HTMLResponse,
    name="tracking_library_action",
)
async def library_row_action(
    request: Request,
    job_id: int,
    action: str,
    state: Annotated[str, Query()] = "all",
    q: Annotated[str, Query()] = "",
    score_min: Annotated[float, Query()] = 0.0,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    """Row-level queue-state actions in the Jobs library.

    `queue` routes through `applications.queue_auto_apply` (creates
    the DRAFT + stamps queued_at + kicks background docs) so a library-queued
    job behaves exactly like a right-swipe. Returns the re-rendered library
    fragment so counts + facets stay truthful.
    """
    import json as _json

    if action not in _LIBRARY_ACTIONS:
        raise HTTPException(status_code=404, detail="Unknown action")
    user_id = _effective_user_id(user)
    target_state, toast = _LIBRARY_ACTIONS[action]

    if action == "queue":
        from models.enums import DocsState
        from services import generation_dispatch, settings_service

        settings = await settings_service.get_or_create(session, user_id=user_id)
        draft = await applications.queue_auto_apply(
            session, user_id=user_id, job_id=job_id, settings=settings
        )
        docs_missing = draft.docs_state in {DocsState.NONE, DocsState.STALE, DocsState.FAILED}
        if docs_missing:
            draft.docs_state = DocsState.GENERATING
        await session.commit()
        if docs_missing:
            generation_dispatch.spawn_generation(draft.id)
    else:
        from services import jobs as job_service

        job = await job_service.set_queue_state(
            session, job_id, user_id=user_id, state=target_state
        )
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        await session.commit()

    ctx = await tctx.build_library_ctx(
        session, user_id=user_id, state=state, q=q, score_min=score_min
    )
    response = templates.TemplateResponse(request, "pages/_tracking_library.html", ctx)
    response.headers["HX-Trigger"] = _json.dumps({"showToast": {"tone": "success", "text": toast}})
    return response


@router.get(
    "/_fragments/tracking/followup-banner",
    response_class=HTMLResponse,
    name="tracking_followup_fragment",
)
async def fragment_followup(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    ctx = await tctx.build_tracking_ctx(session, user_id=_effective_user_id(user), view="board")
    if ctx["followup_count"] == 0:
        return HTMLResponse("")
    return templates.TemplateResponse(
        request,
        "components/followup_banner.html",
        {"count": ctx["followup_count"], "items": ctx["followup_items"]},
    )


# ─────────────────────────────────────────────────────────────────────────
# Application detail slide-over (plan 53 § C / 0.2.4.03)
# ─────────────────────────────────────────────────────────────────────────


async def _application_or_404(session: AsyncSession, application_id: int, user: User | None):
    """Fetch an Application and enforce user_id + soft-delete boundary (IDOR → 404, never 403).

    Plan 86 / 0.4.5.11 — explicit `deleted_at IS NULL` gate aligns with the
    broader soft-delete pattern in `applications.list_applications`;
    soft-deleted rows must not be addressable even by their owner. Uses
    `getattr` to tolerate test fixtures that build minimal `SimpleNamespace`
    application stand-ins without the soft-delete column.
    """
    a = await applications.get_application(session, application_id)
    if (
        a is None
        or a.user_id != _effective_user_id(user)
        or getattr(a, "deleted_at", None) is not None
    ):
        raise HTTPException(status_code=404, detail="Application not found")
    return a


# ─────────────────────────────────────────────────────────────────────────
# Application analytics dashboard (plan 81 § D.4 / 0.4.0.07)
#
# IMPORTANT: literal `/tracking/analytics` MUST be registered BEFORE the
# dynamic `/tracking/{application_id}` route — FastAPI scans routes in
# insertion order. Test: `test_tracking_analytics_route_order_precedence`.
# ─────────────────────────────────────────────────────────────────────────


@router.get("/tracking/analytics", response_class=HTMLResponse, name="tracking_analytics")
async def get_tracking_analytics(
    request: Request,
    window_days: Annotated[int, Query()] = 90,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    """Application KPI dashboard (plan 81 § D.4).

    Pure aggregation over AppEvent + Application — no LLM, no scraper.
    Funnel + 4 KPIs (Applied · Response · Onsite · Offer rates) +
    top-N companies, all scoped to the requester's `user_id`.

    `window_days` is clamped to [1, 365]; default 90 per DATA_MODEL.md § F.
    """
    if window_days < 1 or window_days > 365:
        window_days = 90
    user_id = _effective_user_id(user)
    kpis = await application_analytics.compute_kpis(
        session, user_id=user_id, window_days=window_days
    )
    by_company = await application_analytics.kpis_by_company(
        session, user_id=user_id, window_days=window_days
    )
    by_role_family = await application_analytics.kpis_by_role_family(
        session, user_id=user_id, window_days=window_days
    )
    by_tag = await application_analytics.kpis_by_tag(
        session, user_id=user_id, window_days=window_days
    )
    ctx = {
        "active_sidebar": "tracking",
        "active_template_path": "/tracking",
        "kpis": kpis,
        "by_company": by_company,
        "by_role_family": by_role_family,
        "by_tag": by_tag,
        "window_days": window_days,
    }
    return templates.TemplateResponse(request, "pages/tracking_analytics.html", ctx)


@router.get("/tracking/{application_id}", response_class=HTMLResponse, name="tracking_detail")
async def get_tracking_detail(
    request: Request,
    application_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    application = await _application_or_404(session, application_id, user)
    base_ctx = await tctx.build_tracking_ctx(
        session, user_id=_effective_user_id(user), view="board"
    )
    detail_ctx = await tctx.build_application_detail_ctx(session, application)
    ctx = {**base_ctx, **detail_ctx}
    ctx["active_sidebar"] = "tracking"
    ctx["active_template_path"] = "/tracking"
    ctx["slide_over_open"] = True
    return templates.TemplateResponse(request, "pages/tracking.html", ctx)


@router.get(
    "/_fragments/tracking/application/{application_id}",
    response_class=HTMLResponse,
    name="tracking_application_fragment",
)
async def fragment_application(
    request: Request,
    application_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    application = await _application_or_404(session, application_id, user)
    ctx = await tctx.build_application_detail_ctx(session, application)
    return templates.TemplateResponse(request, "components/_application_detail.html", ctx)


# ─────────────────────────────────────────────────────────────────────────
# Plan 81 § D.1 (0.4.0.10) — postmortem modal overlay
# ─────────────────────────────────────────────────────────────────────────


@router.get(
    "/_modal/postmortem/{application_id}/{ts}",
    response_class=HTMLResponse,
    name="tracking_postmortem_modal",
)
async def get_postmortem_modal(
    request: Request,
    application_id: int,
    ts: str,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    """Render the postmortem-modal partial for `application_id` + `ts`.

    Path-traversal gauntlet matches `api.applications.get_postmortem` (plan 52):
    1. Strict UTC-timestamp regex on `ts` (`_POSTMORTEM_TS_RE`).
    2. `Path.resolve().relative_to(data_root)` containment check.
    3. IDOR via `_application_or_404` (404 on cross-user / missing).
    """
    # IDOR + existence check first — never leak postmortem existence to
    # non-owners by varying the 404/400 code based on app presence.
    await _application_or_404(session, application_id, user)
    if not _POSTMORTEM_TS_RE.match(ts):
        raise HTTPException(status_code=404, detail="postmortem not found")
    data_root = Path(app_settings.data_dir).expanduser().resolve() / "data" / "postmortems"
    base = (data_root / str(application_id) / ts).resolve()
    try:
        base.relative_to(data_root)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="postmortem not found") from exc

    trace_file = base / "trace.json"
    analysis_file = base / "analysis.md"
    if not trace_file.exists() or not analysis_file.exists():
        raise HTTPException(status_code=404, detail="postmortem not found")

    try:
        trace = json.loads(trace_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        trace = {}
    analysis_md = analysis_file.read_text(encoding="utf-8")

    return templates.TemplateResponse(
        request,
        "components/postmortem_modal.html",
        {
            "application_id": application_id,
            "ts": ts,
            "trace": trace,
            "analysis_md": analysis_md,
        },
    )


# ─────────────────────────────────────────────────────────────────────────
# Plan 81 § D.2 (0.4.0.12) — full AppEvent history fragment
# ─────────────────────────────────────────────────────────────────────────


# Per-kind icon + tone for the full-history rendering. Status changes reuse
# the existing dot-color map; other kinds get neutral / accent colors.
_TIMELINE_KIND_DECOR: dict[str, dict[str, str]] = {
    "status_change": {"icon": "arrow-right", "tone": "text-indigo-300"},
    "docs_generated": {"icon": "file-check", "tone": "text-emerald-300"},
    "docs_failed": {"icon": "file-x", "tone": "text-rose-300"},
    "referral_requested": {"icon": "user-plus", "tone": "text-sky-300"},
    "referral_provided": {"icon": "user-check", "tone": "text-emerald-300"},
    "email_received": {"icon": "mail", "tone": "text-cyan-300"},
    "email_sent": {"icon": "send", "tone": "text-indigo-300"},
    "linkedin_dm_sent": {"icon": "linkedin", "tone": "text-sky-300"},
    "linkedin_dm_replied": {"icon": "message-square", "tone": "text-emerald-300"},
    "note_added": {"icon": "sticky-note", "tone": "text-slate-300"},
    "interview_scheduled": {"icon": "calendar", "tone": "text-amber-300"},
    "auto_apply_dry_run": {"icon": "play", "tone": "text-slate-400"},
    "auto_apply_drained": {"icon": "minus-circle", "tone": "text-slate-400"},
    "auto_apply_visa_blocked": {"icon": "shield-off", "tone": "text-rose-300"},
    "auto_apply_queued": {"icon": "refresh-cw", "tone": "text-cyan-300"},
}


@router.get(
    "/_fragments/tracking/timeline/{application_id}",
    response_class=HTMLResponse,
    name="tracking_timeline_fragment",
)
async def fragment_timeline(
    request: Request,
    application_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    """Return the full AppEvent history (limit 100) for a single application.

    Used by the "Show full history" toggle in the detail slide-over. IDOR-
    gated via `_application_or_404`.
    """
    await _application_or_404(session, application_id, user)
    events = await applications.list_events_for(session, application_id, limit=100)

    from ui.tracking_ctx import _relative_label  # local import — avoid cycle

    rows = []
    for e in events:
        decor = _TIMELINE_KIND_DECOR.get(
            e.kind.value if hasattr(e.kind, "value") else str(e.kind),
            {"icon": "circle", "tone": "text-slate-400"},
        )
        payload = e.payload or {}
        label = ""
        if e.kind == AppEventKind.STATUS_CHANGE:
            frm = payload.get("from")
            to = payload.get("to")
            label = f"{frm} → {to}" if frm else (to or "")
        else:
            label = (e.kind.value if hasattr(e.kind, "value") else str(e.kind)).replace("_", " ")
        rows.append(
            {
                "kind": e.kind.value if hasattr(e.kind, "value") else str(e.kind),
                "label": label,
                "icon": decor["icon"],
                "tone": decor["tone"],
                "trigger": payload.get("trigger"),
                "occurred_at_label": _relative_label(e.occurred_at),
            }
        )
    return templates.TemplateResponse(
        request,
        "components/_application_timeline_full.html",
        {"application_id": application_id, "events": rows},
    )


# ─────────────────────────────────────────────────────────────────────────
# Plan 81 § D.3 (0.4.0.16) — notes blur autosave
# ─────────────────────────────────────────────────────────────────────────


_NOTES_MAX_CHARS = 2000


class NotesPayload(BaseModel):
    """Notes-write body (plan 86 / 0.4.5.10).

    `max_length=2000` fires at the Pydantic validator layer so an oversize
    payload is rejected BEFORE the route body runs — eliminates the DoS
    amplification where a 50MB JSON body parsed before the manual cap.
    """

    notes: str = Field(min_length=0, max_length=_NOTES_MAX_CHARS)


@router.put("/api/v1/applications/{application_id}/notes", name="api_applications_put_notes")
async def put_application_notes(
    request: Request,
    application_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    """Persist `Application.notes` from the detail slide-over textarea.

    Boundary checks:
    - CSRF-gated via `require_csrf`.
    - IDOR via `_application_or_404` (404 on cross-user / soft-deleted).
    - Accepts form-encoded (HTMX default) OR JSON; 422 on missing `notes` or
      overflow (cap 2000 chars enforced via `NotesPayload` validator).
    """
    application = await _application_or_404(session, application_id, user)
    content_type = (request.headers.get("content-type") or "").lower()
    if "application/json" in content_type:
        try:
            raw_payload = await request.json()
        except Exception:  # noqa: BLE001 — invalid JSON treated as missing notes
            raw_payload = {}
        if not isinstance(raw_payload, dict):
            raw_payload = {}
    else:
        form = await request.form()
        raw_payload = dict(form.items())

    try:
        payload = NotesPayload.model_validate(raw_payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    text = payload.notes.strip()
    application.notes = text or None
    session.add(application)
    await session.commit()
    # 204 renders nothing — the toast is the only save confirmation the
    # slide-over textarea gives (items 3+4 universal feedback).
    response = Response(status_code=204)
    response.headers["HX-Trigger"] = json.dumps(
        {"showToast": {"tone": "success", "text": "Notes saved."}}
    )
    return response


# ─────────────────────────────────────────────────────────────────────────
# Item 5 (2026-07) — inferred-application confirm / dismiss
# ─────────────────────────────────────────────────────────────────────────


@router.post(
    "/api/v1/applications/{application_id}/inferred/confirm",
    name="api_inferred_confirm",
)
async def post_inferred_confirm(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    from services.email import inference

    ok = await inference.confirm(
        session, user_id=_effective_user_id(user), application_id=application_id
    )
    if not ok:
        raise HTTPException(status_code=404, detail="No pending inferred application")
    await session.commit()
    # Full refresh: the banner row leaves AND the card appears in APPLIED —
    # that state change IS the feedback.
    response = Response(status_code=204)
    response.headers["HX-Refresh"] = "true"
    return response


@router.post(
    "/api/v1/applications/{application_id}/inferred/dismiss",
    name="api_inferred_dismiss",
)
async def post_inferred_dismiss(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    from services.email import inference

    ok = await inference.dismiss(
        session, user_id=_effective_user_id(user), application_id=application_id
    )
    if not ok:
        raise HTTPException(status_code=404, detail="No pending inferred application")
    await session.commit()
    response = Response(status_code=204)
    response.headers["HX-Trigger"] = json.dumps(
        {
            "removeElement": {"selector": f"#inferred-pending-{application_id}"},
            "showToast": {
                "tone": "info",
                "text": "Dismissed — the job stays in your library, untracked.",
            },
        }
    )
    return response


# ─────────────────────────────────────────────────────────────────────────
# Plan 86 § W3.2 / 0.4.5.08 — per-application bullet override toggle
# ─────────────────────────────────────────────────────────────────────────


_BULLET_OVERRIDE_STATES = (None, "always_include", "never_include")


class BulletOverridePayload(BaseModel):
    """Form-encoded body for the bullet-override cycle endpoint."""

    bullet_id: int = Field(ge=1)
    current: str = Field(default="", max_length=20)


@router.put(
    "/api/v1/applications/{application_id}/bullet-override",
    response_class=HTMLResponse,
    name="api_applications_put_bullet_override",
)
async def put_bullet_override(
    request: Request,
    application_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    """Cycle a bullet's per-application override: null → always → never → null.

    Plan 86 / 0.4.5.08. Override lives at
    `Application.submission_artifacts["bullet_overrides"][bullet_id]`.
    Returns the re-rendered bullets-used section so the toggle pill updates
    in place via HTMX outerHTML swap.
    """
    application = await _application_or_404(session, application_id, user)
    form = await request.form()
    try:
        payload = BulletOverridePayload.model_validate(dict(form.items()))
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    current_idx = (
        _BULLET_OVERRIDE_STATES.index(payload.current)
        if payload.current in (s for s in _BULLET_OVERRIDE_STATES if s)
        else 0
    )
    next_state = _BULLET_OVERRIDE_STATES[(current_idx + 1) % len(_BULLET_OVERRIDE_STATES)]

    artifacts = dict(application.submission_artifacts or {})
    overrides = dict(artifacts.get("bullet_overrides") or {})
    key = str(payload.bullet_id)
    if next_state is None:
        overrides.pop(key, None)
    else:
        overrides[key] = next_state
    artifacts["bullet_overrides"] = overrides
    application.submission_artifacts = artifacts
    session.add(application)
    await session.commit()

    detail_ctx = await tctx.build_application_detail_ctx(session, application)
    return templates.TemplateResponse(
        request,
        "components/_application_detail.html",
        {**detail_ctx, "csrf_token": ""},
    )


# ─────────────────────────────────────────────────────────────────────────
# JSON stubs for application moves + manual entry + status overrides
# ─────────────────────────────────────────────────────────────────────────


@router.post(
    "/api/v1/applications/{application_id}/retry",
    name="applications_retry",
)
async def post_retry_application(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    """Plan 79 / 0.4.0.11 — clear `last_failure` + re-queue stuck DRAFT."""
    try:
        await applications.retry_failed(session, application_id, user_id=_effective_user_id(user))
    except applications.IllegalStateTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except applications.ApplicationServiceError:
        raise HTTPException(status_code=404, detail="Application not found") from None
    await session.commit()
    return Response(status_code=204, headers={"HX-Trigger": "applicationRetried"})


@router.post("/api/v1/applications/manual", name="applications_manual")
async def post_application_manual(
    request: Request,
    company: Annotated[str, Form()],
    role: Annotated[str, Form()],
    team: Annotated[str | None, Form()] = None,
    location: Annotated[str | None, Form()] = None,
    salary_min: Annotated[int | None, Form()] = None,
    salary_max: Annotated[int | None, Form()] = None,
    notes: Annotated[str | None, Form()] = None,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    """Create a manually-entered Application (plan 56 / 0.2.7.19 — CSRF-gated)."""
    await applications.create_manual(
        session,
        user_id=_effective_user_id(user),
        company=company,
        role=role,
        team=team,
        location=location,
        salary_min=salary_min,
        salary_max=salary_max,
        notes=notes,
    )
    await session.commit()
    response = Response(status_code=204)
    response.headers["HX-Redirect"] = "/tracking"
    return response


@router.get("/api/v1/applications", name="applications_list")
async def get_applications(
    status: Annotated[str | None, Query()] = None,
    closed: Annotated[int, Query()] = 0,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    user_id = _effective_user_id(user)
    if status:
        try:
            status_enum = ApplicationStatus(status)
        except ValueError:
            raise HTTPException(status_code=422, detail="Unknown status") from None
        apps = await applications.list_by_status(session, user_id, status_enum)
    elif closed:
        apps = await applications.list_closed(session, user_id)
    else:
        apps = await applications.list_visible_in_tracking(session, user_id)
    return {"items": [a.model_dump(mode="json") for a in apps], "next_cursor": None}


_EXPORT_FIELDNAMES = [
    "company",
    "role",
    "team",
    "location",
    "status",
    "applied_at",
    "salary_min",
    "salary_max",
    "board",
    "external_url",
]


# Registered BEFORE the parameterized `/applications/{application_id}` so
# the literal `export.csv` path doesn't get parsed as an int application_id.
@router.get("/api/v1/applications/export.csv", name="applications_export_csv")
async def get_applications_export_csv(
    application_ids: Annotated[list[int] | None, Query()] = None,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    """Export selected applications as CSV. Auth-gated; cap 50 IDs."""
    user_id = _effective_user_id(user)
    ids = application_ids or []
    try:
        rows = await applications.list_for_export(
            session,
            user_id=user_id,
            application_ids=ids,
        )
    except applications.ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_EXPORT_FIELDNAMES)
    writer.writeheader()
    writer.writerows(rows)
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="applications.csv"',
        },
    )


@router.get("/api/v1/applications/{application_id}", name="applications_get")
async def get_application(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    a = await applications.get_application(session, application_id)
    if a is None or a.user_id != _effective_user_id(user):
        raise HTTPException(status_code=404, detail="Application not found")
    return a.model_dump(mode="json")


@router.get("/api/v1/applications/{application_id}/bundle", name="applications_bundle")
async def get_application_bundle(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    """Download the REAL generated bundle for an application as a ZIP.

    Was a stub that zipped placeholder ("%PDF-1.4\\n%placeholder") bytes. Now
    reads the actual generated resume/cover-letter PDFs off disk and includes
    the real screener answers. Returns 409 (not a fake ZIP) when nothing has
    been generated yet, so the user gets an honest "generate first" signal.
    """
    import io
    import json as _json
    import zipfile
    from pathlib import Path as _Path

    a = await applications.get_application(session, application_id)
    if a is None or a.user_id != _effective_user_id(user):
        raise HTTPException(status_code=404, detail="Application not found")

    docs = await applications.latest_documents(session, application_id)
    screeners = await applications.list_screener_answers_for(session, application_id)

    if not docs:
        raise HTTPException(
            status_code=409,
            detail="No generated documents yet — generate the bundle first.",
        )

    buf = io.BytesIO()
    included = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "metadata.json",
            _json.dumps(
                {
                    "application_id": application_id,
                    "company": a.company,
                    "role": a.role,
                    "documents": [d.kind.value for d in docs],
                },
                indent=2,
            ),
        )
        for d in docs:
            path = _Path(d.path)
            if path.exists() and path.is_file():
                zf.write(path, arcname=f"{d.kind.value.lower()}.pdf")
                included += 1
        zf.writestr(
            "screener-answers.json",
            _json.dumps(
                [{"question": s.question_text, "answer": s.answer} for s in screeners],
                indent=2,
            ),
        )

    if included == 0:
        raise HTTPException(
            status_code=409,
            detail="Generated document files are missing on disk — regenerate the bundle.",
        )

    buf.seek(0)
    return Response(
        content=buf.read(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="bundle-{application_id}.zip"'},
    )


# ─────────────────────────────────────────────────────────────────────────
# Bulk actions on /tracking list view (plan 80 / 0.4.0.09)
# ─────────────────────────────────────────────────────────────────────────


def _bulk_toast_header(success: int, failed: int) -> str:
    return json.dumps({"showToast": {"text": f"Updated {success}, skipped {failed}"}})


@router.post(
    "/_fragments/tracking/bulk/move-stage",
    response_class=HTMLResponse,
    name="tracking_bulk_move_stage",
)
async def post_bulk_move_stage(
    request: Request,
    application_ids: Annotated[list[int], Form()],
    new_status: Annotated[str, Form()],
    closed_reason: Annotated[str | None, Form()] = None,
    show_drafts: Annotated[int, Form()] = 0,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    """Bulk-move selected applications to ``new_status``.

    Returns the updated tracking list fragment + an ``HX-Trigger`` toast
    summary. 422 on unknown enum or > 50 IDs.
    """
    try:
        status_enum = ApplicationStatus(new_status)
    except ValueError:
        raise HTTPException(status_code=422, detail="Unknown status") from None
    cr_enum: ClosedReason | None
    if closed_reason:
        try:
            cr_enum = ClosedReason(closed_reason)
        except ValueError:
            raise HTTPException(status_code=422, detail="Unknown closed_reason") from None
    else:
        cr_enum = None

    user_id = _effective_user_id(user)
    try:
        success, failed = await applications.bulk_update_status(
            session,
            user_id=user_id,
            application_ids=application_ids,
            new_status=status_enum,
            closed_reason=cr_enum,
        )
    except applications.ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    await session.commit()

    ctx = await tctx.build_tracking_ctx(
        session,
        user_id=user_id,
        view="list",
        show_closed=True,
        show_drafts=bool(show_drafts),
    )
    response = templates.TemplateResponse(request, "pages/_tracking_list.html", ctx)
    response.headers["HX-Trigger"] = _bulk_toast_header(success, len(failed))
    return response


@router.post(
    "/_fragments/tracking/bulk/archive",
    response_class=HTMLResponse,
    name="tracking_bulk_archive",
)
async def post_bulk_archive(
    request: Request,
    application_ids: Annotated[list[int], Form()],
    show_drafts: Annotated[int, Form()] = 0,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    """Bulk archive — closes selected applications w/ USER_ARCHIVED reason."""
    user_id = _effective_user_id(user)
    try:
        success, failed = await applications.bulk_archive(
            session,
            user_id=user_id,
            application_ids=application_ids,
        )
    except applications.ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    await session.commit()

    ctx = await tctx.build_tracking_ctx(
        session,
        user_id=user_id,
        view="list",
        show_closed=True,
        show_drafts=bool(show_drafts),
    )
    response = templates.TemplateResponse(request, "pages/_tracking_list.html", ctx)
    response.headers["HX-Trigger"] = _bulk_toast_header(success, len(failed))
    return response
