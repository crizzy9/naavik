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

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from api.auth import require_csrf
from config import settings as app_settings
from db.session import get_session
from models import User
from services import profile as profile_service
from services.auth import get_current_user, require_password_complete
from services.settings import env_secrets
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
        "pages/auth/login.html",
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
        "pages/auth/onboarding.html",
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
        "pages/auth/change_password.html",
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
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_password_complete),
    _csrf: None = Depends(require_csrf),
):
    """Receive a resume PDF, persist it under `<data_dir>/uploads/<user_id>/`,
    extract plaintext via `pdfplumber`, persist the text on `Profile.raw_resume_text`,
    heuristically populate empty identity fields (full_name / email / phone),
    and return a confirmation partial.

    Plan 0.7.0.48 Wave 3 fold-in (2026-05-25): Wave 2 dropped the extracted
    text on the floor. Now we persist + heuristically backfill empty profile
    identity fields (regex only — no LLM call per owner directive). Operator
    hand-edits are never overwritten.

    Plan 0.7.0.48 Wave 2 hacker MED fold-in (2026-05-25): `require_csrf`
    enforces double-submit on this state-changing route. The dropzone form
    inherits the global `hx-headers='{"X-CSRF-Token": ...}'` from
    `base.html`, so the dependency fires cleanly on HTMX-driven uploads;
    direct curl callers need to send both the `naavik_csrf` cookie + the
    `X-CSRF-Token` header (issued at signup/login).
    """
    if resume.content_type not in {"application/pdf", "application/x-pdf"}:
        raise HTTPException(status_code=422, detail="Only PDF uploads are supported.")

    # Capture eagerly: after a mid-request DB failure the ORM instance is
    # expired and `user.id` would lazy-load on a poisoned session (turning a
    # gracefully-degradable parse failure into a 500 in the except blocks).
    user_id = user.id

    payload = await resume.read()
    if len(payload) == 0:
        raise HTTPException(status_code=422, detail="Uploaded file is empty.")
    if len(payload) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB cap.",
        )

    upload_dir = Path(app_settings.data_dir) / "uploads" / str(user_id)
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

    # Best-effort persistence: the PDF is already on disk regardless.
    # `set_raw_resume_text` flushes the TX (per service-layer convention);
    # this route owns the commit (mirrors `src/api/profile.py:put_profile_bulk`
    # + every other state-changing handler in the codebase). Without this
    # commit the TX rolls back at request end + `raw_resume_text` never
    # persists. (Plan 0.7.0.48 W3-followup fix — owner manual QA round 3
    # surfaced raw_resume_text NULL post-upload despite the service call
    # firing cleanly.)
    try:
        await profile_service.set_raw_resume_text(session, user_id, extracted)
        await session.commit()
    except Exception as exc:  # noqa: BLE001 — persistence is best-effort
        log.warning("set_raw_resume_text failed user=%s: %s", user_id, exc)
        await session.rollback()

    # Structured parse: when an LLM provider is configured, run the full
    # PDF → AI → Profile pipeline so the profile is populated with real
    # experiences + bullets (not just identity fields). This is the fix for
    # the long-standing "resume parse only filled the summary" bug — the
    # `extract_to_profile` pipeline already existed but was never wired into
    # the upload flow. When no provider is configured we fall back to the
    # regex identity backfill below so onboarding still makes progress.
    structured_ok = False
    experiences_added = 0
    parsed_summary: dict | None = None
    parse_error: str | None = None
    llm_missing = False
    try:
        from llm import LLMProviderError
        from services import settings as settings_service
        from services.profile import extraction

        user_settings = await settings_service.get_or_create(session, user_id=user_id)
        # `resolve_usable_llm_provider` (not the plain resolver): Ollama's
        # baked-in localhost default otherwise makes "no provider configured"
        # unreachable, and the parse dies against a dead endpoint with a raw
        # connection error instead of the friendly guidance below.
        if await env_secrets.resolve_usable_llm_provider() is None:
            llm_missing = True
        else:
            await extraction.extract_to_profile(
                session,
                user_id=user_id,
                settings=user_settings,
                pdf_path=target,
            )
            await session.commit()
            structured_ok = True
            parsed_summary = await _parsed_profile_summary(session, user_id)
            experiences_added = len(parsed_summary["experiences"])
    except LLMProviderError as exc:
        log.warning("structured resume parse LLM failure user=%s: %s", user_id, exc)
        await session.rollback()
        if exc.kind == "auth_required":
            llm_missing = True
        else:
            parse_error = str(exc)
    except extraction.ExtractionError as exc:
        log.warning("structured resume parse failed user=%s: %s", user_id, exc)
        await session.rollback()
        parse_error = str(exc)
    except Exception as exc:  # noqa: BLE001 — never fail the upload on parse issues
        log.warning("structured resume parse errored user=%s: %s", user_id, exc)
        await session.rollback()
        parse_error = str(exc)

    # Seed job-search preferences from the fresh parse (current title +
    # location) so a new user reaches Discover results without touching
    # Settings, then expand titles (degrades to raw titles with no LLM).
    # Best-effort: never fail the upload on preference seeding.
    try:
        from services.jobs import search_prefs

        profile_row = await profile_service.get_profile(session, user_id)
        if profile_row is not None:
            seeded = await search_prefs.prefill_search_prefs(session, profile=profile_row)
            if seeded:
                from services import settings as _settings_service

                user_settings = await _settings_service.get_or_create(session, user_id=user_id)
                await search_prefs.refresh_title_expansions(
                    session, profile=profile_row, settings=user_settings
                )
            await session.commit()
    except Exception as exc:  # noqa: BLE001
        log.warning("search-pref prefill failed user=%s: %s", user_id, exc)
        await session.rollback()

    log.info(
        "extraction upload user=%s file=%s bytes=%d chars=%d structured=%s experiences=%d",
        user_id,
        safe_name,
        len(payload),
        len(extracted),
        structured_ok,
        experiences_added,
    )

    # Explicit completion feedback (P5 universal-feedback convention): the
    # parse can take 30s+, so the swap alone is easy to miss — every outcome
    # also fires a toast via HX-Trigger (wired in base.js).
    if structured_ok:
        toast = {
            "text": f"Resume parsed — {experiences_added} experience"
            f"{'' if experiences_added == 1 else 's'} with bullets added to your profile.",
            "tone": "success",
        }
    elif llm_missing:
        toast = {
            "text": "Resume text saved, but no AI provider is reachable — "
            "configure one in Settings to auto-structure your profile.",
            "tone": "warning",
        }
    elif parse_error:
        toast = {
            "text": "Resume uploaded, but AI parsing failed — details on screen.",
            "tone": "warning",
        }
    else:
        toast = {"text": "Resume uploaded.", "tone": "success"}

    return templates.TemplateResponse(
        request,
        "pages/auth/_onboarding_step_uploaded.html",
        {
            "chars": len(extracted),
            "filename": safe_name,
            "structured": structured_ok,
            "experiences_added": experiences_added,
            "parsed": parsed_summary,
            "parse_error": parse_error,
            "llm_missing": llm_missing,
        },
        headers={"HX-Trigger": json.dumps({"showToast": toast})},
    )


async def _parsed_profile_summary(session: AsyncSession, user_id: int) -> dict:
    """What the parse produced — rendered on the confirmation screen so the
    user can verify success without navigating away."""
    profile = await profile_service.get_profile(session, user_id)
    experiences = await profile_service.list_experiences(session, user_id)
    educations = await profile_service.list_educations(session, user_id)
    projects = await profile_service.list_projects(session, user_id)
    skills = await profile_service.list_skills(session, user_id)

    exp_views = []
    for exp in experiences:
        bullets = await profile_service.get_bullets_for_experience(session, exp.id)
        exp_views.append({"company": exp.company, "title": exp.title, "bullets": len(bullets)})

    return {
        "full_name": profile.full_name if profile else None,
        "email": profile.email if profile else None,
        "phone": profile.phone if profile else None,
        "experiences": exp_views,
        "educations": [e.institution for e in educations],
        "projects": [p.title for p in projects],
        "skill_groups": len(skills),
    }
