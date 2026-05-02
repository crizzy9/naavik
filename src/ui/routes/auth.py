"""Auth-shell HTML pages: `/login`, `/onboarding`.

Wave 4 of plan 10 § B.3 moves the JSON `/api/v1/auth/*` handlers to
`src/api/auth.py` (real bcrypt + JWT + CSRF). The plan-09 stubs that lived
here for `/api/v1/auth/login`, `/api/v1/auth/logout`, `/api/v1/auth/me`,
`/api/v1/auth/csrf` are deleted; the page handlers below stay.

`/api/v1/extraction/*` and `/api/v1/profile/from-extraction` remain stubs
until Wave 6 — they need the extraction service which is Phase 1 work but
not on Wave 4's critical path.
"""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse

from ui.auth_stub import FAKE_SESSION_VALUE, SESSION_COOKIE
from ui.templates_setup import templates

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────
# Page handlers
# ─────────────────────────────────────────────────────────────────────────


@router.get("/login", response_class=HTMLResponse, name="login")
async def get_login(request: Request):
    return templates.TemplateResponse(
        request,
        "pages/login.html",
        {
            "active_sidebar": None,
            "active_template_path": "/login",
        },
    )


@router.get("/onboarding", response_class=HTMLResponse, name="onboarding")
async def get_onboarding(request: Request, step: Annotated[int, Query(ge=1, le=3)] = 1):
    return templates.TemplateResponse(
        request,
        "pages/onboarding.html",
        {
            "active_sidebar": None,
            "active_template_path": "/onboarding",
            "current_step": step,
        },
    )


# ─────────────────────────────────────────────────────────────────────────
# /api/v1/extraction — Onboarding step-2 stubs (Wave 6 makes these real)
# ─────────────────────────────────────────────────────────────────────────


@router.post("/api/v1/extraction/upload", name="extraction_upload")
async def post_extraction_upload(
    request: Request,
    fail: Annotated[str | None, Query()] = None,
):
    """Stub PDF upload — returns the Step-2 (extracting) partial so HTMX can
    swap it into `#onboarding-step-content` (per the dropzone wiring).
    """
    if fail:
        return HTMLResponse(
            content=(
                '<div class="p-4 rounded-lg bg-rose-500/10 border border-rose-500/30 '
                'text-rose-200 text-sm">Upload failed. Try a different file.</div>'
            ),
            status_code=422,
        )
    return templates.TemplateResponse(
        request,
        "pages/_onboarding_step_extracting.html",
        {"extraction_id": "fake-1"},
    )


@router.get("/api/v1/extraction/{extraction_id}/stream", name="extraction_stream")
async def get_extraction_stream(extraction_id: str):
    """SSE — 5 progress, 6 field, 1 done, 1 stepReady events over ~6s.

    `stepReady` carries an OOB swap whose `hx-trigger="load delay:200ms"`
    auto-progresses the page to Step 3.
    """

    fields = [
        ("extracted-field-row-name", "NAME", "Shyam Padia", 0.99),
        ("extracted-field-row-title", "TITLE", "Senior Software Engineer · Intuit", 0.96),
        ("extracted-field-row-location", "LOCATION", "San Francisco, CA", 0.92),
        ("extracted-field-row-experience", "EXPERIENCE", "8 years · 4 roles", 0.88),
        ("extracted-field-row-skills", "SKILLS", "Python, ML, distributed systems", 0.85),
        ("extracted-field-row-education", "EDUCATION", "MS CS Northeastern · BE Mumbai", 0.93),
    ]

    async def event_gen():
        for pct in (15, 40, 60, 80, 95):
            yield (
                'event: progress\ndata: <div id="extraction-progress" '
                'hx-swap-oob="outerHTML">'
                f'<div class="text-xs font-mono uppercase tracking-wide text-slate-400">{pct}%</div>'
                "</div>\n\n"
            )
            await asyncio.sleep(0.4)
        for fid, label, value, conf in fields:
            html = (
                f'<div id="{fid}" hx-swap-oob="outerHTML" '
                'class="flex items-baseline gap-3 py-1.5 border-b border-slate-800/50">'
                f'<span class="font-mono text-[11px] uppercase tracking-wide text-slate-500 w-20 shrink-0">{label}</span>'
                f'<span class="text-sm flex-1 text-slate-200">{value}</span>'
                f'<span class="font-mono text-xs text-emerald-400 ml-auto tabular-nums">{conf:.2f}</span>'
                "</div>"
            )
            yield f"event: field\ndata: {html}\n\n"
            await asyncio.sleep(0.4)
        yield (
            'event: done\ndata: <div id="extraction-status" hx-swap-oob="outerHTML" '
            'class="inline-flex items-center gap-2 text-sm text-emerald-300 font-medium">'
            '<svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">'
            '<polyline points="20 6 9 17 4 12"/></svg>'
            "Extracted 6 of 6 fields."
            "</div>\n\n"
        )
        yield (
            'event: stepReady\ndata: <div id="extraction-trigger" hx-swap-oob="outerHTML" '
            'hx-get="/_fragments/onboarding/step/3" hx-target="#onboarding-step-content" '
            'hx-trigger="load delay:200ms">progressing…</div>\n\n'
        )

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@router.post("/api/v1/profile/from-extraction", name="profile_from_extraction")
async def post_profile_from_extraction(request: Request):
    """Stub — flag the profile committed and redirect / via HX-Redirect.

    Wave 6 wires this to `services/profile_service.commit_extraction`.
    """
    response = Response(status_code=204)
    response.headers["HX-Redirect"] = "/"
    response.set_cookie(
        SESSION_COOKIE,
        FAKE_SESSION_VALUE,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return response
