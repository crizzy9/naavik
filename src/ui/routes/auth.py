"""Auth-shell HTML pages: `/login`, `/onboarding`.

Wave 4 of plan 10 § B.3 moves the JSON `/api/v1/auth/*` handlers to
`src/api/auth.py` (real bcrypt + JWT + CSRF). The plan-09 stubs that lived
here for `/api/v1/auth/login`, `/api/v1/auth/logout`, `/api/v1/auth/me`,
`/api/v1/auth/csrf` are deleted; the page handlers below stay.

Plan 0.7.0.48 Wave 2 (2026-05-25): the SSE-extraction stubs + the
`post_profile_from_extraction` fake-session bridge are deleted.
`post_extraction_upload` now receives a real PDF, persists it, extracts
text via `pdfplumber`, and returns a confirmation partial that links to
`/profile/edit`. Onboarding collapses from 3 steps to 1.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse

from config import settings as app_settings
from models import User
from services.auth import get_current_user, require_password_complete
from ui.templates_setup import templates

log = logging.getLogger(__name__)

router = APIRouter()


# Max upload size enforced server-side (browser file-picker can't truly cap).
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


# ─────────────────────────────────────────────────────────────────────────
# Page handlers
# ─────────────────────────────────────────────────────────────────────────


@router.get("/login", response_class=HTMLResponse, name="login")
async def get_login(
    request: Request,
    mode: Annotated[str | None, Query(pattern="^(signin|signup)$")] = None,
):
    """Login page. `?mode=signup` swaps the form into account-creation mode
    (plan 10b item 4 — replaces the dead `?create=1` link). Open signup is
    the default per plan 0.7.0.48 — no server-side gate suppresses the
    form anymore.
    """
    resolved_mode = mode or "signin"
    return templates.TemplateResponse(
        request,
        "pages/login.html",
        {
            "active_sidebar": None,
            "active_template_path": "/login",
            "mode": resolved_mode,
        },
    )


@router.get("/onboarding", response_class=HTMLResponse, name="onboarding")
async def get_onboarding(request: Request):
    """Single-step onboarding: upload a resume PDF, then hand off to
    `/profile/edit`. Plan 0.7.0.48 Wave 2 (2026-05-25) collapses the prior
    3-step SSE stub flow.
    """
    return templates.TemplateResponse(
        request,
        "pages/onboarding.html",
        {
            "active_sidebar": None,
            "active_template_path": "/onboarding",
        },
    )


@router.get(
    "/auth/change-password",
    response_class=HTMLResponse,
    name="change_password_page",
)
async def get_change_password(
    request: Request,
    user: User = Depends(get_current_user),
):
    """Plan 18 (PC.6, 2026-05-17): forced-rotation page. Reached when the
    user's `must_change_password` flag is True. The page also renders when
    the flag is False (voluntary password change); the must-change banner
    only appears when flagged. Uses bare `get_current_user` (not
    `require_password_complete`) so a flagged user can actually reach it.
    """
    return templates.TemplateResponse(
        request,
        "pages/change_password.html",
        {
            "active_sidebar": None,
            "active_template_path": "/auth/change-password",
            "must_change": user.must_change_password,
            "email": user.email,
        },
    )


# ─────────────────────────────────────────────────────────────────────────
# /api/v1/extraction/upload — resume PDF receive + text extract
# ─────────────────────────────────────────────────────────────────────────


@router.post("/api/v1/extraction/upload", name="extraction_upload")
async def post_extraction_upload(
    request: Request,
    resume: UploadFile,
    user: User = Depends(require_password_complete),
):
    """Receive a resume PDF, persist it under `<data_dir>/uploads/<user_id>/`,
    extract plaintext via `pdfplumber`, and return a confirmation partial.

    Plan 0.7.0.48 Wave 2 (2026-05-25): replaces the prior SSE+fake-session
    stub. No LLM call — pdfplumber raw text only. The extracted text is
    not yet persisted to Profile (operator fills profile fields manually);
    persistence is a future plan once we have an LLM-driven extractor.
    """
    if resume.content_type not in {"application/pdf", "application/x-pdf"}:
        raise HTTPException(status_code=422, detail="Only PDF uploads are supported.")

    payload = await resume.read()
    if len(payload) == 0:
        raise HTTPException(status_code=422, detail="Uploaded file is empty.")
    if len(payload) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB cap.",
        )

    upload_dir = Path(app_settings.data_dir) / "uploads" / str(user.id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
    safe_name = Path(resume.filename or "resume.pdf").name
    target = upload_dir / f"{ts}.pdf"
    target.write_bytes(payload)

    # pdfplumber raw extract — pure Python, no system deps. Failures
    # surface to the user as a friendly 422 (not 500) since the user can
    # try a different PDF.
    import pdfplumber

    try:
        with pdfplumber.open(target) as pdf:
            chunks: list[str] = []
            for page in pdf.pages:
                text = page.extract_text() or ""
                if text:
                    chunks.append(text)
            extracted = "\n".join(chunks)
    except Exception as exc:  # noqa: BLE001 — bubble pdfplumber failures
        log.warning("pdfplumber extract failed for %s: %s", target, exc)
        raise HTTPException(
            status_code=422,
            detail="Couldn't read that PDF. Try a different file.",
        ) from exc

    log.info(
        "extraction upload user=%s file=%s bytes=%d chars=%d",
        user.id,
        safe_name,
        len(payload),
        len(extracted),
    )

    return templates.TemplateResponse(
        request,
        "pages/_onboarding_step_uploaded.html",
        {
            "chars": len(extracted),
            "filename": safe_name,
        },
    )
