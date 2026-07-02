"""Real `/api/v1/applications/*` handlers — Wave 6.

Per BACKEND.md § D.4 + plan 10 § C.3. Replaces the stubs that lived under
`ui/routes/tracking.py` (move/discard/submit) with service-layer-backed
handlers that go through `application_service.submit_draft / discard_draft /
update_status`.

Page handlers (`GET /tracking`, etc.) stay in `ui/routes/`; only the JSON
mutation endpoints move here.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Response
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from api.auth import require_csrf
from config import settings as app_settings
from db.session import get_session
from models import ApplicationStatus, ClosedReason, Settings, User
from services import application_service as svc
from services.auth import require_password_complete
from services.bundle_generator import generate_bundle, regenerate_cover_letter
from services.rate_limit import check_generate_bundle_rate_limit

_REGENERATE_KIND_VALID = {"bundle", "cover_letter", "resume"}

_POSTMORTEM_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z$")

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/applications")


@router.post("/{application_id}/submit", name="api_applications_submit")
async def submit(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_password_complete),
):
    """DRAFT → APPLIED. Validates first; returns the row or 409 with the reason.

    Plan 85 / 0.4.0.21 — IDOR boundary: 404 on cross-user / missing app.
    Mirrors plan 75 row 1 screener-IDOR pattern; matches `generate_bundle_route`
    + `get_postmortem` precedent in this module.
    """
    application = await svc.get_application(session, application_id)
    if application is None or application.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Application not found")
    try:
        out = await svc.submit_draft(session, application_id)
    except svc.ValidationError as exc:
        raise HTTPException(
            status_code=409, detail={"code": exc.code, "message": str(exc)}
        ) from exc
    except svc.ApplicationServiceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    # Caller (HTMX) wants HX-Redirect on success.
    if out.status == ApplicationStatus.APPLIED:
        await session.commit()
        response = Response(status_code=204)
        response.headers["HX-Redirect"] = "/tracking"
        return response

    # Persistent failure — caller renders banner from submission_artifacts.
    last_failure = (out.submission_artifacts or {}).get("last_failure", {})
    return {
        "id": out.id,
        "status": out.status.value,
        "last_failure": last_failure,
    }


@router.delete("/{application_id}/discard", name="api_applications_discard")
async def discard(
    application_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_password_complete),
):
    """DRAFT → CLOSED (withdrawn_by_me) + soft-delete.

    Plan 85 / 0.4.0.21 — IDOR boundary: 404 on cross-user / missing app.
    """
    application = await svc.get_application(session, application_id)
    if application is None or application.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Application not found")
    try:
        await svc.discard_draft(session, application_id)
    except svc.IllegalStateTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except svc.ApplicationServiceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    response = Response(status_code=204)
    response.headers["HX-Redirect"] = "/discover"
    return response


@router.put("/{application_id}/status", name="api_applications_put_status")
async def put_status(
    application_id: int,
    payload: Annotated[dict[str, Any], Body()],
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_password_complete),
):
    """Manual status flip (e.g. APPLIED → RECRUITER_SCREEN).

    Plan 85 / 0.4.0.21 — IDOR boundary: 404 on cross-user / missing app.
    """
    application = await svc.get_application(session, application_id)
    if application is None or application.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Application not found")
    raw = payload.get("status")
    if not raw:
        raise HTTPException(status_code=422, detail="`status` required")
    try:
        new_status = ApplicationStatus(raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Unknown status {raw!r}") from exc
    cr = payload.get("closed_reason")
    closed_reason = None
    if new_status == ApplicationStatus.CLOSED:
        if not cr:
            raise HTTPException(
                status_code=422,
                detail="`closed_reason` required when status=CLOSED",
            )
        try:
            closed_reason = ClosedReason(cr)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"Unknown closed_reason {cr!r}") from exc
    try:
        out = await svc.update_status(
            session,
            application_id,
            new_status,
            closed_reason=closed_reason,
            notes=payload.get("notes"),
        )
    except svc.ValidationError as exc:
        raise HTTPException(
            status_code=409, detail={"code": exc.code, "message": str(exc)}
        ) from exc
    except svc.ApplicationServiceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    return out.model_dump(mode="json")


@router.post("/move", name="api_applications_move")
async def move(
    payload: Annotated[dict[str, Any] | None, Body()] = None,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_password_complete),
):
    """Tracking-board column move (drag-drop status change).

    Plan 85 / 0.4.0.21 — IDOR boundary: 404 on cross-user / missing app.
    Empty / malformed payloads still short-circuit to 204 (pre-IDOR
    behavior preserved — the IDOR check fires once we have an app_id).
    """
    if not payload:
        return Response(status_code=204)
    app_id = int(payload.get("application_id", 0))
    target = payload.get("target_status")
    if not (app_id and target):
        return Response(status_code=204)
    application = await svc.get_application(session, app_id)
    if application is None or application.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Application not found")
    try:
        new_status = ApplicationStatus(target)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Bad status") from exc
    closed_reason = None
    if new_status == ApplicationStatus.CLOSED:
        cr = payload.get("closed_reason")
        if cr:
            closed_reason = ClosedReason(cr)
    try:
        await svc.update_status(session, app_id, new_status, closed_reason=closed_reason)
    except svc.ApplicationServiceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    return Response(status_code=204)


@router.get("/{application_id}/postmortem/{ts}", name="api_applications_postmortem")
async def get_postmortem(
    application_id: int,
    ts: str,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_password_complete),
):
    """Return the ATS-failure postmortem for one application + timestamp.

    IDOR boundary: 404 on cross-user / missing app (no existence leak).
    Path-traversal guard: strict UTC-timestamp regex + `resolve().relative_to()`.
    """
    app = await svc.get_application(session, application_id)
    if app is None or app.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Application not found")
    if not _POSTMORTEM_TS_RE.match(ts):
        raise HTTPException(status_code=400, detail="invalid timestamp")

    data_root = Path(app_settings.data_dir).expanduser().resolve() / "data" / "postmortems"
    base = (data_root / str(application_id) / ts).resolve()
    try:
        base.relative_to(data_root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid path") from exc

    trace_file = base / "trace.json"
    analysis_file = base / "analysis.md"
    if not trace_file.exists() or not analysis_file.exists():
        raise HTTPException(status_code=404, detail="postmortem not found")

    trace = json.loads(trace_file.read_text(encoding="utf-8"))
    analysis_md = analysis_file.read_text(encoding="utf-8")
    return {"trace": trace, "analysis_markdown": analysis_md}


@router.post("/{application_id}/generate-bundle", name="api_applications_generate_bundle")
async def generate_bundle_route(
    application_id: int,
    payload: Annotated[dict[str, Any] | None, Body()] = None,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_password_complete),
    _csrf: None = Depends(require_csrf),
    _rate_limit: None = Depends(check_generate_bundle_rate_limit),
):
    """One-click bundle generation for `application_id` (plan 66 / 0.3.1).

    Returns the bundle metadata + audit trail. The PDFs themselves are
    served via the existing `GeneratedDocument.path` download endpoint.

    IDOR boundary: 404 on cross-user / missing app. Cost-cap mid-flight
    surfaces as `degraded: true` + `degraded_reason: "cost_cap_reached"`.
    Ethics rejection (> 2 bullets fabricated) returns 422.
    Plan 75 / 0.3.3.06 — rate limited 10/hr per user.
    """
    application = await svc.get_application(session, application_id)
    if application is None or application.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Application not found")

    settings = (
        await session.exec(select(Settings).where(Settings.user_id == current_user.id))
    ).one_or_none()
    if settings is None:
        raise HTTPException(status_code=409, detail="Settings missing for user")

    hiring_manager_override = None
    regenerate_kind = "bundle"
    if payload is not None:
        raw = payload.get("hiring_manager_override")
        if isinstance(raw, str) and raw.strip():
            hiring_manager_override = raw.strip()
        raw_kind = payload.get("regenerate_kind")
        if raw_kind is not None:
            if not isinstance(raw_kind, str) or raw_kind not in _REGENERATE_KIND_VALID:
                raise HTTPException(
                    status_code=422,
                    detail=(f"regenerate_kind must be one of {sorted(_REGENERATE_KIND_VALID)}"),
                )
            regenerate_kind = raw_kind

    try:
        if regenerate_kind == "cover_letter":
            bundle = await regenerate_cover_letter(
                session,
                application,
                settings=settings,
                hiring_manager_override=hiring_manager_override,
            )
        else:
            bundle = await generate_bundle(
                session,
                application,
                settings=settings,
                hiring_manager_override=hiring_manager_override,
            )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if bundle.ethics is not None and bundle.ethics.surface_to_user and not bundle.ethics.passed:
        await session.commit()
        raise HTTPException(
            status_code=422,
            detail={
                "code": "ethics_pre_flight_failed",
                "message": "LLM emitted bullets without profile provenance.",
                "dropped_bullets": bundle.ethics.dropped_bullets,
            },
        )

    await session.commit()
    response: dict[str, Any] = {
        "resume_id": bundle.resume.id if bundle.resume else None,
        "cover_letter_id": bundle.cover_letter.id if bundle.cover_letter else None,
        "screeners_count": len(bundle.screeners),
        "degraded": bundle.degraded,
        "degraded_reason": bundle.degraded_reason,
        "parse_fidelity_score": (bundle.parse_fidelity.score if bundle.parse_fidelity else None),
        "parse_fidelity_tier": (bundle.parse_fidelity.tier if bundle.parse_fidelity else None),
        "keyword_coverage_score": (
            bundle.keyword_coverage.score if bundle.keyword_coverage else None
        ),
        "hiring_manager": (
            {
                "name": bundle.hiring_manager.name,
                "source": bundle.hiring_manager.source,
                "confidence": bundle.hiring_manager.confidence,
            }
            if bundle.hiring_manager
            else None
        ),
        "generation_trace": bundle.generation_trace,
    }
    # P5: every outcome fires a body event base.js turns into a toast —
    # this route's main HTMX caller uses hx-swap="none", so without a
    # trigger the whole generation was silent.
    if bundle.degraded:
        trigger = "bundle-degraded"
    elif bundle.parse_fidelity and bundle.parse_fidelity.tier == "toast":
        trigger = "parse-fidelity-warning"
    else:
        trigger = "bundle-generated"
    return Response(
        content=json.dumps(response),
        media_type="application/json",
        headers={"HX-Trigger": trigger},
    )


@router.get("/stuck", name="api_applications_stuck")
async def get_stuck(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_password_complete),
):
    """Stuck-queue endpoint — DRAFTs with `submission_artifacts.last_failure`.

    Vault boundary: scoped to the current user. Powers the Discover right
    rail "Stuck in queue" card.
    """
    apps = await svc.stuck_drafts(session, user_id=current_user.id)
    return {
        "items": [
            {
                "id": a.id,
                "company": a.company,
                "role": a.role,
                "board": a.board.value if a.board else None,
                "last_failure": (a.submission_artifacts or {}).get("last_failure"),
            }
            for a in apps
        ]
    }
