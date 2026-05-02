"""Auth-shell routes (Login, Onboarding) + auth JSON stubs for plan 09.

Plan 10 Wave 4 swaps the JSON stubs (`/api/v1/auth/*`, `/api/v1/extraction/*`,
`/api/v1/profile/from-extraction`) for real bcrypt + JWT + extraction-service
implementations. Page-handler signatures stay the same.
"""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse

from db import sample_data as sd
from ui.auth_stub import FAKE_SESSION_VALUE, SESSION_COOKIE, is_authenticated
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
# /api/v1/auth — JSON stubs (BACKEND.md § D.1)
# ─────────────────────────────────────────────────────────────────────────


@router.post("/api/v1/auth/login", name="auth_login")
async def post_login(
    request: Request,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    keep_signed_in: Annotated[str | None, Form()] = None,
    fail: Annotated[str | None, Query()] = None,
):
    """Stub login — sets `naavik_session=fake-1` cookie + redirects.

    `?fail=1` returns 401 with an inline error fragment (HTMX swaps into
    `#login-card`). Sentinel email `onboarding@test` redirects to `/onboarding`.
    """
    if fail:
        return HTMLResponse(
            content=_login_error_card("Invalid credentials. Try again."),
            status_code=401,
        )
    if not email or not password:
        return HTMLResponse(
            content=_login_error_card("Email and password are required."),
            status_code=422,
        )
    redirect_to = "/onboarding" if email.strip().lower() == "onboarding@test" else "/"
    response = Response(status_code=204)
    response.headers["HX-Redirect"] = redirect_to
    response.set_cookie(
        SESSION_COOKIE,
        FAKE_SESSION_VALUE,
        httponly=True,
        samesite="lax",
        max_age=(60 * 60 * 24 * 30) if keep_signed_in else None,
        path="/",
    )
    return response


@router.post("/api/v1/auth/logout", name="auth_logout")
async def post_logout(request: Request):
    response = Response(status_code=204)
    response.headers["HX-Redirect"] = "/login"
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@router.get("/api/v1/auth/me", name="auth_me")
async def get_me(request: Request):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = await sd.get_user()
    return user.model_dump(mode="json")


@router.get("/api/v1/auth/csrf", name="auth_csrf")
async def get_csrf(request: Request):
    """Stub CSRF token. Plan 10 Wave 4 rotates on auth events."""
    return {"csrf_token": "fake-csrf-token-1"}


# ─────────────────────────────────────────────────────────────────────────
# /api/v1/extraction — Onboarding step-2 stubs
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
    """Stub — flag the profile committed and redirect / via HX-Redirect."""
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


# ─────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────


def _login_error_card(message: str) -> str:
    safe = message.replace("<", "&lt;").replace(">", "&gt;")
    return (
        '<div id="login-card" class="w-full max-w-[440px] bg-slate-900 border '
        'border-slate-800 rounded-xl p-7 shadow-2xl shadow-black/45">'
        '<div class="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 '
        'text-rose-200 text-sm" role="alert">' + safe + "</div>"
        '<p class="mt-4 text-xs text-slate-500">'
        '<a href="/login" class="text-indigo-400 hover:text-indigo-300">'
        "← Back to sign in</a></p>"
        "</div>"
    )
