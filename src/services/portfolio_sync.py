"""Portfolio sync — public CV API + cached generic resume + Netlify webhook.

Per BACKEND.md § L (Portfolio) + plan 10 § C.6.

The portfolio API exposes a filtered Profile (no email/phone/EEO/visa/salary)
to the configured CORS origin(s). The generic resume PDF lives at
`~/.naavik/data/documents/portfolio/resume.pdf` and is regenerated on Profile
edits, debounced 60s. The Netlify rebuild webhook fires alongside the regen.

CORS origins are configurable via `Settings.portfolio_cors_allowed_origins`.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from config import settings as app_settings
from models import Profile, Settings

log = logging.getLogger(__name__)

DEFAULT_DEBOUNCE_SECONDS = 60.0


# ── Public CV payload (filtered) ───────────────────────────────────────


_FILTERED_PROFILE_FIELDS = frozenset(
    {
        # PII
        "email",
        "phone",
        # Compensation
        "salary_expectation_usd",
        # EEO
        "veteran_status",
        "disability_status",
        "race_ethnicity",
        "gender_identity",
        # Visa
        "work_authorization",
        "visa_sponsorship_needed",
        # Operational
        "willing_to_relocate",
        "notice_period_days",
        "earliest_start",
    }
)


def public_cv_payload(
    profile: Profile, *, experiences=None, skills=None, education=None, projects=None
) -> dict[str, Any]:
    """Filter a Profile (+ optional related rows) for the public API.

    Strips email/phone/EEO/visa/salary. Returns plain JSON-serializable dict.
    """
    pdict: dict[str, Any] = {}
    for key in (
        "id",
        "user_id",
        "full_name",
        "headline",
        "current_company",
        "location",
        "portfolio_url",
        "github_handle",
        "linkedin_handle",
        "summary_full",
        "summary_short",
        "open_to_opportunities",
        "created_at",
        "updated_at",
    ):
        val = getattr(profile, key, None)
        if isinstance(val, datetime):
            val = val.isoformat()
        pdict[key] = val
    return {
        "profile": pdict,
        "experiences": [_serialize_experience(e) for e in (experiences or [])],
        "skills": [{"category": s.category, "items": list(s.items or [])} for s in (skills or [])],
        "education": [_serialize_education(e) for e in (education or [])],
        "projects": [_serialize_project(p) for p in (projects or [])],
    }


def _serialize_experience(exp) -> dict[str, Any]:
    return {
        "company": exp.company,
        "title": getattr(exp, "title", None) or getattr(exp, "role", None),
        "team": getattr(exp, "team", None),
        "location": exp.location,
        "start_date": exp.start_date.isoformat() if exp.start_date else None,
        "end_date": exp.end_date.isoformat() if exp.end_date else None,
        "summary_short": getattr(exp, "summary_short", None),
    }


def _serialize_education(edu) -> dict[str, Any]:
    return {
        "institution": edu.institution,
        "degree": edu.degree,
        "start_date": edu.start_date.isoformat() if edu.start_date else None,
        "end_date": edu.end_date.isoformat() if edu.end_date else None,
        "gpa": edu.gpa,
    }


def _serialize_project(proj) -> dict[str, Any]:
    return {
        "title": proj.title,
        "text": proj.text,
        "link": proj.link,
        "tags": list(getattr(proj, "tags", []) or []),
    }


def assert_no_pii(payload: dict[str, Any]) -> None:
    """Defensive assertion — used by tests to verify nothing leaked."""
    pdict = payload.get("profile") or {}
    for filt in _FILTERED_PROFILE_FIELDS:
        if filt in pdict:
            raise ValueError(f"PII leak: {filt!r} present in public CV payload")


# ── CORS allowlist ─────────────────────────────────────────────────────


def cors_allowed_origins(settings: Settings) -> list[str]:
    raw = settings.portfolio_cors_allowed_origins or []
    return [o for o in raw if o]


def is_cors_allowed(settings: Settings, origin: str | None) -> bool:
    if not origin:
        return False
    allowed = cors_allowed_origins(settings)
    return origin in allowed


# ── Cached portfolio resume PDF ────────────────────────────────────────


def portfolio_resume_path() -> Path:
    raw = app_settings.data_dir
    base = Path(raw).expanduser() if raw.startswith("~") else Path(raw)
    if not base.is_absolute():
        base = base.resolve()
    return base / "data" / "documents" / "portfolio" / "resume.pdf"


# Module-level debounce state — process-wide so concurrent edits coalesce.
_debounce_handle: asyncio.TimerHandle | None = None
_debounce_task: asyncio.Task | None = None


async def regenerate_generic_resume(
    *, settings: Settings, generate_fn=None, session=None, user_id: int = 1
) -> Path | None:
    """Compile the generic resume PDF + cache at the canonical path.

    `generate_fn` defaults to `document_generator.generate_generic_resume`;
    tests inject a stub. Returns the compiled path on success, None on failure.
    """
    if generate_fn is None:
        from services.document_generator import (
            generate_generic_resume as generate_fn,  # type: ignore[no-redef]
        )
    out_path = portfolio_resume_path()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = await generate_fn(
            session,
            user_id=user_id,
            settings=settings,
            output_path=out_path,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("portfolio resume regen failed: %s", exc)
        return None
    if result is None:
        return None
    return out_path


# ── Netlify rebuild webhook (debounced) ────────────────────────────────


async def trigger_netlify_rebuild(*, http_client: httpx.AsyncClient | None = None) -> bool:
    """Fire the Netlify build hook configured via `PORTFOLIO_WEBHOOK_URL` env."""
    url = app_settings.portfolio_webhook_url
    if not url:
        return False
    client = http_client or httpx.AsyncClient(timeout=10.0)
    owns = http_client is None
    try:
        resp = await client.post(url, json={"trigger": "naavik-profile-update"})
        if resp.status_code >= 300:
            log.warning("netlify rebuild failed: %d", resp.status_code)
            return False
        return True
    except httpx.RequestError as exc:
        log.warning("netlify rebuild errored: %s", exc)
        return False
    finally:
        if owns:
            await client.aclose()


def schedule_debounced_regen(
    *,
    settings: Settings,
    session=None,
    user_id: int = 1,
    delay_seconds: float = DEFAULT_DEBOUNCE_SECONDS,
    fire_netlify: bool = True,
) -> None:
    """Schedule (or reset) a debounced regen + Netlify webhook.

    Intended to be called from `profile_service.update_*` paths (Phase 1
    fires from the route handler; future plans wire into AppEvent listeners).
    Subsequent calls within `delay_seconds` reset the timer.
    """
    global _debounce_handle, _debounce_task

    loop = asyncio.get_event_loop()

    async def _do_work():
        try:
            await regenerate_generic_resume(settings=settings, session=session, user_id=user_id)
            if fire_netlify:
                await trigger_netlify_rebuild()
        except Exception as exc:  # noqa: BLE001
            log.warning("debounced regen errored: %s", exc)

    def _fire():
        nonlocal_task = loop.create_task(_do_work())
        # Track the task so we can await it during shutdown.
        global _debounce_task  # noqa: PLW0603
        _debounce_task = nonlocal_task

    if _debounce_handle is not None:
        _debounce_handle.cancel()
    _debounce_handle = loop.call_later(delay_seconds, _fire)
