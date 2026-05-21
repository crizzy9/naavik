"""Settings page + tab routes + per-tab JSON / SSE stubs (BACKEND.md § D.7).

Plan 26 (0.2.0.01): the encrypted vault is gone. The API-key fragment
endpoint (`/_fragments/settings/llm/api-key-field`) is deleted along with
its template; the LLM tab now renders env-presence indicators instead of
an input. Deployment-tab context drops the vault-locked banner triplet.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from db import sample_data as sd
from db.session import get_session
from models import JobScrapeRunRead, JobSource, User
from services import application_service, env_secrets, job_service, llm_tracker, settings_service
from services.auth import require_authed_session, require_password_complete
from ui.templates_setup import templates

router = APIRouter()


_TAB_TEMPLATES: dict[str, str] = {
    "llm-provider": "pages/_settings_llm.html",
    "deployment": "pages/_settings_deployment.html",
    "account": "pages/_settings_account.html",
    "notifications": "pages/_settings_notifications.html",
    "auto-apply": "pages/_settings_auto_apply.html",
    "sources": "pages/_settings_sources.html",
    "submissions": "pages/_settings_submissions.html",
    "security": "pages/_settings_security.html",
}

_VALID_TABS = set(_TAB_TEMPLATES.keys())


_PROVIDERS_DISPLAY = [
    {
        "id": "anthropic",
        "name": "Anthropic Claude",
        "model_default": "claude-3.5-sonnet-20250219",
        "description": "Recommended · best resume bullet quality.",
        "kind": "CLOUD",
        "env_var": "ANTHROPIC_API_KEY",
    },
    {
        "id": "openai",
        "name": "OpenAI GPT",
        "model_default": "gpt-4o",
        "description": "Faster, slightly cheaper.",
        "kind": "CLOUD",
        "env_var": "OPENAI_API_KEY",
    },
    {
        "id": "ollama",
        "name": "Ollama (Local)",
        "model_default": "llama3.1:70b",
        "description": "Llama 3.1 70B on your machine · private.",
        "kind": "LOCAL",
        "env_var": "OLLAMA_BASE_URL",
    },
]


# Plan 10b (item 6, 2026-05-03): per-provider model catalog driving the
# Settings · LLM Provider model dropdown. Kept inline (not in DB) — these
# are SDK-supported model IDs at the time of release, not user-managed data.
_LLM_MODEL_OPTIONS: dict[str, list[str]] = {
    "anthropic": [
        "claude-3.5-sonnet-20250219",
        "claude-3.5-haiku-20250219",
        "claude-3-opus-20240229",
    ],
    "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
    "ollama": ["llama3.1:70b", "llama3.1:8b", "qwen2.5:32b"],
}


def _llm_model_options_for(provider_id: str) -> list[str]:
    return list(_LLM_MODEL_OPTIONS.get(provider_id, []))


def _llm_default_model_for(provider_id: str) -> str:
    options = _LLM_MODEL_OPTIONS.get(provider_id, [])
    return options[0] if options else ""


_LOG_LINES_SEED = [
    {
        "timestamp": "14:02:41",
        "level": "INFO",
        "message": "discover.fetch  · pulled 24 jobs from greenhouse · 312ms",
    },
    {
        "timestamp": "14:02:41",
        "level": "INFO",
        "message": "discover.match  · scored 24 jobs · avg fit 71%",
    },
    {
        "timestamp": "14:03:02",
        "level": "INFO",
        "message": "apply.submit    · zed industries / sr fullstack · ok · 4.2s",
    },
    {
        "timestamp": "14:03:18",
        "level": "INFO",
        "message": "resume.tailor   · llm=claude-3.5-sonnet · 412ms · 1184 tok",
    },
    {
        "timestamp": "14:03:18",
        "level": "INFO",
        "message": "cover.draft     · llm=claude-3.5-sonnet · 689ms · 2104 tok",
    },
    {
        "timestamp": "14:04:55",
        "level": "WARN",
        "message": "tracking.imap   · gmail oauth token refreshing · 1 retry",
    },
    {
        "timestamp": "14:05:14",
        "level": "ERROR",
        "message": "apply.submit    · vercel / sr designer · captcha required → moved to review queue",
    },
    {
        "timestamp": "14:05:30",
        "level": "INFO",
        "message": "outreach.send   · 3 linkedin DMs queued · sending in 4m",
    },
    {
        "timestamp": "14:05:48",
        "level": "INFO",
        "message": "db.snapshot     · ~/.naavik/data/snapshots/2026-04-29.sql.gz",
    },
]


# Plan 26 (0.2.0.01): SECRETS row replaced; CONFIG row now points at .env.
_ON_DISK = [
    {
        "label": "DATA DIR",
        "path": "~/.naavik/data",
        "sub": "412 MB · 27 jobs · 14 applications",
        "icon": "folder",
    },
    {
        "label": "CONFIG",
        "path": ".env",
        "sub": "env-loaded · gitignored",
        "icon": "file-cog",
    },
    {
        "label": "SNAPSHOTS",
        "path": "~/.naavik/snapshots/",
        "sub": "8 daily · auto-prune at 30",
        "icon": "archive",
    },
]


# ─────────────────────────────────────────────────────────────────────────
# Page handlers
# ─────────────────────────────────────────────────────────────────────────


async def _ctx_for_tab(
    request: Request,
    tab: str,
    *,
    session: AsyncSession | None = None,
    user_id: int = 1,
) -> dict[str, object]:
    if tab not in _VALID_TABS:
        raise HTTPException(status_code=404, detail="Unknown settings tab")
    settings = await sd.get_settings()
    cost_summary = await sd.llm_usage_summary(days=30)
    provider_id = settings.llm_provider.value if settings else "anthropic"
    deployment_info = await _deployment_render_info(settings)

    ctx: dict[str, object] = {
        "current_tab": tab,
        "tab_template": _TAB_TEMPLATES[tab],
        "settings": settings,
        "profile": await sd.get_profile(),
        "providers": _PROVIDERS_DISPLAY,
        "cost_summary": cost_summary,
        # Plan 10b (item 6): LLM tab fragment context — the form template
        # resolves model + env-indicator state from these. The model fragment
        # endpoint below builds the same context for HTMX swaps.
        "provider_id": provider_id,
        "model_options": _llm_model_options_for(provider_id),
        "selected_model": settings.llm_model or _llm_default_model_for(provider_id),
        "env_indicators": env_secrets.env_indicators_for_llm_tab(),
        "notify_env_indicators": env_secrets.env_indicators_for_notifications_tab(),
        "save_status": None,
        "deployment": deployment_info,
        "log_lines": _LOG_LINES_SEED,
        "on_disk": _ON_DISK,
        "active_sidebar": "settings",
        "active_template_path": "/settings/:tab" if tab != "llm-provider" else "/settings",
    }

    if tab == "sources":
        ctx["sources_view"] = await _build_sources_view(session, user_id=user_id)
        ctx["recent_scrape_runs"] = await _recent_scrape_runs_view(session, user_id=user_id)

    if tab == "submissions":
        ctx["submission_failures"] = await _submission_failures_view(session, user_id=user_id)
        # Plan 63 / 0.2.7.10 § C.6 — ATS adapter credential presence indicators.
        ctx["ats_credential_indicators"] = env_secrets.ats_credential_indicators()

    if tab == "llm-provider":
        today_cost, cap = await _llm_cost_cap_view(session, settings, user_id=user_id)
        ctx["today_cost_usd"] = today_cost
        ctx["cost_cap_usd"] = cap

    if tab == "security":
        ctx["security"] = await _build_security_view(session, user_id=user_id)

    return ctx


# ── Plan 54 / 0.2.5 dashboard views ────────────────────────────────────


async def _recent_scrape_runs_view(
    session: AsyncSession | None, *, user_id: int
) -> list[JobScrapeRunRead]:
    """List recent JobScrapeRun rows projected via JobScrapeRunRead.

    Plan 57 / 0.2.7.23 — threads `user_id` through (closes the sibling IDOR
    after plan 56 fixed `_build_sources_view`).
    """
    if session is None:
        return []
    runs = await job_service.list_recent_scrape_runs(session, user_id=user_id, limit=50)
    return [JobScrapeRunRead.model_validate(r, from_attributes=True) for r in runs]


async def _submission_failures_view(session: AsyncSession | None, *, user_id: int) -> list[dict]:
    """Per-(board, failure_kind) Application failure aggregates.

    Plan 57 / 0.2.7.23 — threads `user_id` through (closes the sibling IDOR
    after plan 56 fixed `_build_sources_view`).
    """
    if session is None:
        return []
    return await application_service.aggregate_submission_failures(session, user_id=user_id)


async def _llm_cost_cap_view(
    session: AsyncSession | None, settings, *, user_id: int
) -> tuple[float, float | None]:
    """Today's spend + the configured daily cap (None if unset).

    Plan 57 / 0.2.7.23 — threads `user_id` through (closes the sibling IDOR
    after plan 56 fixed `_build_sources_view`).
    """
    cap = getattr(settings, "daily_llm_cost_cap_usd", None) if settings else None
    if session is None:
        return 0.0, cap
    today = await llm_tracker.today_cost_usd(session, user_id=user_id)
    return today, cap


# ── Sources panel context (plan 49 / 0.2.0.16) ──────────────────────────


_SOURCES_PANEL = [
    {"value": JobSource.LINKEDIN, "label": "LinkedIn", "icon": "linkedin"},
    {"value": JobSource.WORKDAY, "label": "Workday", "icon": "briefcase"},
    {"value": JobSource.GREENHOUSE, "label": "Greenhouse", "icon": "leaf"},
    {"value": JobSource.LEVER, "label": "Lever", "icon": "git-branch"},
    {"value": JobSource.ASHBY, "label": "Ashby", "icon": "globe"},
    {"value": JobSource.INDEED, "label": "Indeed", "icon": "search"},
]

# Fallback cron strings when Settings.source_schedules is empty.
_DEFAULT_SCHEDULES: dict[str, str] = {
    "linkedin": "*/30 * * * *",
    "workday": "0 * * * *",
    "greenhouse": "0 * * * *",
    "lever": "0 * * * *",
    "ashby": "0 * * * *",
    "indeed": "every 90 min",
}

_ENV_VAR_FOR_SOURCE = {
    # Plan 56 / 0.2.7.04: WORKDAY excluded — Workday uses `Settings.workday_companies`
    # (per-user DB); the `WORKDAY_COMPANIES` env-slot in `src/config.py` is dead-letter
    # until 0.2.7.06 wires env→DB seed at boot.
    "greenhouse": "GREENHOUSE_COMPANIES",
    "lever": "LEVER_COMPANIES",
    "ashby": "ASHBY_COMPANIES",
}

_ENV_EXAMPLE_FOR_SOURCE = {
    "greenhouse": "GREENHOUSE_COMPANIES=anthropic,scale,databricks",
    "lever": "LEVER_COMPANIES=netflix,figma",
    "ashby": "ASHBY_COMPANIES=ramp,vercel",
}


def _format_started_at(dt) -> str:
    """Render a human-readable "Nh ago" / "Nm ago" / ISO date for last-run timestamp."""
    from datetime import UTC, datetime

    if dt is None:
        return ""
    now = datetime.now(UTC)
    started = dt
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    delta = now - started
    seconds = max(int(delta.total_seconds()), 0)
    if seconds < 60:
        return f"{seconds}s ago"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    if days < 7:
        return f"{days}d ago"
    return started.strftime("%Y-%m-%d")


def _effective_user_id(user: User | None) -> int:
    """Resolve per-request user_id for IDOR scoping (mirrors `ui.routes.jobs`).

    Real JWT sessions return `user.id`. The fake-session transitional stub
    maps to the seeded owner (id=1) per `db/sample_data.py:USER.id == 1`.
    Plan 56 / `0.2.7.02` — threading this through `_build_sources_view` to
    close the latent IDOR before multi-user expansion.
    """
    return user.id if user is not None else 1


async def _build_sources_view(session: AsyncSession | None, *, user_id: int) -> list[dict]:
    """Compose the per-source view list consumed by `_settings_sources.html`.

    Per plan 49 § D.1 — pulls (a) Settings (SQL row when session present;
    shadow fallback otherwise), (b) latest JobScrapeRun per source via
    `job_service.list_recent_scrape_runs_by_source`, (c) env-vs-DB
    configured indicator via `env_secrets.scraper_source_configured`,
    (d) resolved rate-limit via `scraper.rate_limit.resolve_rate_limit`.
    """
    from config import settings as app_settings
    from scraper.rate_limit import resolve_rate_limit

    if session is None:
        # Plan 56 / 0.2.7.03 — defense in depth. The /settings/sources route
        # always provides a session via Depends(get_session); reaching this
        # branch means a caller forgot the dep wiring. Raise loudly so the
        # bug surfaces instead of degrading to a silently-empty panel.
        raise RuntimeError(
            "_build_sources_view requires an AsyncSession — "
            "callers must pass Depends(get_session) (plan 49 / 0.2.0.16 contract)"
        )

    settings_obj = await settings_service.get_or_create(session, user_id=user_id)
    last_runs = await job_service.list_recent_scrape_runs_by_source(session, user_id=user_id)

    rows: list[dict] = []
    for entry in _SOURCES_PANEL:
        source: JobSource = entry["value"]
        source_value = source.value
        sources_enabled = getattr(settings_obj, "sources_enabled", {}) or {}
        source_schedules = getattr(settings_obj, "source_schedules", {}) or {}
        configured = env_secrets.scraper_source_configured(source, settings_obj)
        rate_limit = resolve_rate_limit(settings_obj, source)
        run = last_runs.get(source)
        last_run_view: dict | None = None
        if run is not None:
            if run.status.value == "running" or run.finished_at is None:
                status_value = "running"
            else:
                status_value = run.status.value
            last_run_view = {
                "status_value": status_value,
                "started_at_label": _format_started_at(run.started_at),
            }
        configure_block: dict
        if source is JobSource.WORKDAY:
            # Plan 56 / 0.2.7.04 — Workday's cron reads `Settings.workday_companies`
            # (per-user DB), not `WORKDAY_COMPANIES` env. The env-slot exists in
            # config.py but is dead-letter until 0.2.7.06 wires it. Render honest
            # popover prose under `kind="db-workday"` instead of the misleading
            # env-kind w/ a CSV example operators copy to .env and see no result.
            configure_block = {
                "kind": "db-workday",
                "companies": list(getattr(settings_obj, "workday_companies", None) or []),
            }
        elif source_value in _ENV_VAR_FOR_SOURCE:
            configure_block = {
                "kind": "env",
                "env_var": _ENV_VAR_FOR_SOURCE[source_value],
                "example": _ENV_EXAMPLE_FOR_SOURCE.get(source_value),
            }
            if source is JobSource.GREENHOUSE:
                current = app_settings.greenhouse_companies or []
            elif source is JobSource.LEVER:
                current = app_settings.lever_companies or []
            elif source is JobSource.ASHBY:
                current = app_settings.ashby_companies or []
            else:
                current = []
            if current:
                configure_block["current"] = ", ".join(current)
        else:
            keywords_attr = (
                "linkedin_keywords" if source is JobSource.LINKEDIN else "indeed_keywords"
            )
            location_attr = (
                "linkedin_location" if source is JobSource.LINKEDIN else "indeed_location"
            )
            configure_block = {
                "kind": "db",
                "keywords": list(getattr(settings_obj, keywords_attr, None) or []),
                "location": getattr(settings_obj, location_attr, None) or "",
            }
        rows.append(
            {
                "source": source_value,
                "label": entry["label"],
                "icon": entry["icon"],
                "enabled": bool(sources_enabled.get(source_value, True)),
                "configured": configured,
                "last_run": last_run_view,
                "schedule": source_schedules.get(source_value, _DEFAULT_SCHEDULES[source_value]),
                "rate_limit": {
                    "rpm": rate_limit.rpm,
                    "delay_lo": rate_limit.delay_lo,
                    "delay_hi": rate_limit.delay_hi,
                },
                "configure": configure_block,
            }
        )
    return rows


async def _build_security_view(session: AsyncSession | None, *, user_id: int) -> dict[str, object]:
    """Compose the Settings · Security panel context — plan 62 (0.2.7.07).

    Reads the tenant's ACTIVE + RETIRING signing keys + the Settings
    rotation cadence/grace columns. Self-host single-tenant: tenant_id
    derives from user_id (1:1 mapping until plan `0.8.0.NN` introduces
    a real Tenant↔User mapping).
    """
    from datetime import UTC, datetime, timedelta

    from sqlmodel import func, select

    from models import (
        Settings as SettingsRow,
    )
    from models import (
        TenantSigningKey,
        TenantSigningKeyStatus,
    )

    rotation_days = 90
    rotation_grace_days = 7
    if session is not None:
        # Scalar select avoids loading the full Settings row (JSONB columns
        # tests don't materialize on sqlite). Mirrors the `allow_multi_scalar`
        # pattern in `api/auth.py:post_signup`.
        row = (
            await session.exec(
                select(SettingsRow.jwt_rotation_days, SettingsRow.jwt_rotation_grace_days)
                .where(SettingsRow.user_id == user_id)
                .limit(1)
            )
        ).one_or_none()
        if row is not None:
            rotation_days = int(row[0])
            rotation_grace_days = int(row[1])

    if session is None:
        return {
            "active_key": None,
            "retiring_keys": [],
            "retired_count": 0,
            "rotation_days": rotation_days,
            "rotation_grace_days": rotation_grace_days,
        }

    tenant_id = user_id  # 1:1 self-host mapping (plan 62 § C.9 / D9).

    active = (
        await session.exec(
            select(TenantSigningKey).where(
                TenantSigningKey.tenant_id == tenant_id,
                TenantSigningKey.status == TenantSigningKeyStatus.ACTIVE,
            )
        )
    ).one_or_none()
    retiring_rows = (
        await session.exec(
            select(TenantSigningKey)
            .where(
                TenantSigningKey.tenant_id == tenant_id,
                TenantSigningKey.status == TenantSigningKeyStatus.RETIRING,
            )
            .order_by(TenantSigningKey.retired_at.desc())  # type: ignore[union-attr]
        )
    ).all()
    retired_count_row = await session.exec(
        select(func.count(TenantSigningKey.id)).where(
            TenantSigningKey.tenant_id == tenant_id,
            TenantSigningKey.status == TenantSigningKeyStatus.RETIRED,
        )
    )
    retired_count = int(retired_count_row.one() or 0)

    def _fmt_dt(dt) -> str:
        if dt is None:
            return ""
        return _format_started_at(dt)

    def _expires_in_label(retired_at, grace_days: int) -> str:
        if retired_at is None:
            return "—"
        ra = retired_at if retired_at.tzinfo else retired_at.replace(tzinfo=UTC)
        cutoff = ra + timedelta(days=grace_days)
        delta = cutoff - datetime.now(UTC)
        secs = int(delta.total_seconds())
        if secs <= 0:
            return "any moment"
        days = secs // 86400
        if days >= 1:
            return f"{days}d"
        hours = secs // 3600
        if hours >= 1:
            return f"{hours}h"
        return f"{max(secs // 60, 1)}m"

    return {
        "active_key": (
            {
                "kid": active.kid,
                "algorithm": active.algorithm.value,
                "created_at_label": _fmt_dt(active.created_at),
            }
            if active is not None
            else None
        ),
        "retiring_keys": [
            {
                "kid": row.kid,
                "algorithm": row.algorithm.value,
                "retired_at_label": _fmt_dt(row.retired_at),
                "expires_in_label": _expires_in_label(row.retired_at, rotation_grace_days),
            }
            for row in retiring_rows
        ],
        "retired_count": retired_count,
        "rotation_days": rotation_days,
        "rotation_grace_days": rotation_grace_days,
    }


async def _deployment_render_info(settings) -> dict[str, object]:
    """Build the `deployment` ctx dict consumed by `_settings_deployment.html`.

    Plan 26 (0.2.0.01): vault status fields removed. The template no longer
    renders the rose vault-locked banner.
    """
    mode_value = settings.deployment_mode.value if settings else "self_hosted"
    return {
        "mode": "self-hosted" if mode_value == "self_hosted" else "cloud",
        "status": "active",
        "version": "0.4.2",
        "meta": "docker-compose · uptime 14d 6h · last restart Apr 14",
        "update_available_version": "0.4.3",
    }


@router.get("/settings", response_class=HTMLResponse, name="settings")
async def get_settings(request: Request):
    ctx = await _ctx_for_tab(request, "llm-provider")
    return templates.TemplateResponse(request, "pages/settings.html", ctx)


@router.get("/settings/sources", response_class=HTMLResponse, name="settings_sources")
async def get_settings_sources(
    request: Request,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
):
    """Settings · Sources sub-tab — plan 49 / 0.2.0.16.

    Gated by `require_authed_session` so unauthed callers receive 401 (rest
    of Settings sub-tabs remain unauthed today; the auth tightening for
    other tabs lands as a separate row). `Depends(get_session)` is the
    canonical entry; tests override via `app.dependency_overrides`.
    """
    ctx = await _ctx_for_tab(request, "sources", session=session, user_id=_effective_user_id(_user))
    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(request, "pages/_settings_sources.html", ctx)
    return templates.TemplateResponse(request, "pages/settings.html", ctx)


@router.get("/settings/submissions", response_class=HTMLResponse, name="settings_submissions")
async def get_settings_submissions(
    request: Request,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
):
    """Settings · Submissions sub-tab — plan 54 / 0.2.5.02.

    Aggregated failure-kind dashboard per ATS adapter. Gated by
    `require_authed_session` mirroring the Sources sub-tab pattern;
    `Depends(get_session)` is the canonical entry. Plan 57 / 0.2.7.23 —
    threads `_effective_user_id` to close sibling IDOR.
    """
    ctx = await _ctx_for_tab(
        request, "submissions", session=session, user_id=_effective_user_id(_user)
    )
    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(request, "pages/_settings_submissions.html", ctx)
    return templates.TemplateResponse(request, "pages/settings.html", ctx)


@router.get(
    "/settings/llm-provider",
    response_class=HTMLResponse,
    name="settings_llm_provider",
)
async def get_settings_llm_provider(
    request: Request,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
):
    """Settings · LLM Provider tab with daily cost-cap widget — plan 54 / 0.2.5.03.

    Dedicated route (vs. catch-all `/settings/{tab}`) so we can `Depends(get_session)`
    without changing the catch-all's signature (existing tests rely on it being
    DB-free). Plan 56 / 0.2.7.20 — gated by `require_authed_session` matching the
    Sources + Submissions sub-tabs; the daily-cost widget aggregates per-user
    ApiUsage rows and shouldn't leak unauth. Plan 57 / 0.2.7.23 — threads
    `_effective_user_id` to close sibling IDOR.
    """
    ctx = await _ctx_for_tab(
        request, "llm-provider", session=session, user_id=_effective_user_id(_user)
    )
    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(request, "pages/_settings_llm.html", ctx)
    return templates.TemplateResponse(request, "pages/settings.html", ctx)


@router.get("/settings/security", response_class=HTMLResponse, name="settings_security")
async def get_settings_security(
    request: Request,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
):
    """Settings · Security sub-tab — plan 62 (0.2.7.07).

    Shows active + retiring JWT signing keys + the "Rotate now" button.
    Gated by `require_authed_session` mirroring the Sources sub-tab pattern;
    `Depends(get_session)` is the canonical entry. `_effective_user_id`
    threads through to close the IDOR — never read another tenant's keys.
    """
    ctx = await _ctx_for_tab(
        request, "security", session=session, user_id=_effective_user_id(_user)
    )
    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(request, "pages/_settings_security.html", ctx)
    return templates.TemplateResponse(request, "pages/settings.html", ctx)


@router.get("/settings/{tab}", response_class=HTMLResponse, name="settings_tab")
async def get_settings_tab(request: Request, tab: str):
    if tab not in _VALID_TABS:
        raise HTTPException(status_code=404, detail="Unknown settings tab")
    ctx = await _ctx_for_tab(request, tab)
    return templates.TemplateResponse(request, "pages/settings.html", ctx)


# ─────────────────────────────────────────────────────────────────────────
# JSON / fragment stubs
# ─────────────────────────────────────────────────────────────────────────


# Plan 10b (item 6, 2026-05-03): the duplicate `PUT /api/v1/settings/llm`
# stub that previously lived here was deleted. The real handler in
# `src/api/settings.py:put_llm` now serves both JSON and HTMX form clients.
# `post_llm_test` stays here because it produces the
# `components/connection_status_card.html` fragment that the LLM tab's
# "Test connection" button mounts via /_fragments/settings/test-connection.


async def post_llm_test(request: Request, fail: Annotated[str | None, Query()] = None):
    """LLM connectivity-test fragment renderer used by the test-connection button.

    Returns an HTML card; the upstream button swaps the result into
    `#llm-test-result`. JSON-style probe of the live provider lives in
    `src/api/settings.py:post_llm_test` under the same path; the form's
    button calls the fragment route below, not the API.
    """
    await asyncio.sleep(0.4)
    if fail:
        return templates.TemplateResponse(
            request,
            "components/connection_status_card.html",
            {
                "ok": False,
                "provider": "Anthropic API",
                "error_code": 401,
                "error_message": "Unauthorized",
            },
        )
    return templates.TemplateResponse(
        request,
        "components/connection_status_card.html",
        {"ok": True, "latency_ms": 412, "model": "claude-3.5-sonnet-20250219"},
    )


@router.get("/api/v1/settings/llm/usage", name="settings_llm_usage")
async def get_llm_usage(period: Annotated[str, Query()] = "month"):
    return await sd.llm_usage_summary(days=30 if period == "month" else 7)


@router.put("/api/v1/settings/auto-apply", name="settings_auto_apply_put")
async def put_auto_apply(
    request: Request,
    _user: User | None = Depends(require_authed_session),
):
    return {"ok": True}


@router.put("/api/v1/settings/sources", name="settings_sources_put")
async def put_sources(
    request: Request,
    _user: User | None = Depends(require_authed_session),
):
    return {"ok": True}


@router.put("/api/v1/settings/notifications", name="settings_notifications_put")
async def put_notifications(
    request: Request,
    _user: User | None = Depends(require_authed_session),
):
    return {"ok": True}


@router.post("/api/v1/settings/notifications/test", name="settings_notifications_test")
async def post_notifications_test(
    request: Request,
    channel: Annotated[Literal["discord", "telegram"], Query()],
    fail: Annotated[str | None, Query()] = None,
    _user: User | None = Depends(require_authed_session),
):
    if fail:
        return HTMLResponse(
            f'<span class="text-rose-300">Couldn\'t reach {channel}.</span>',
            status_code=502,
        )
    return HTMLResponse(f'<span class="text-emerald-300">Sent test {channel} message.</span>')


@router.get("/api/v1/settings/deployment", name="settings_deployment_get")
async def get_deployment():
    settings = await sd.get_settings()
    return {
        "mode": settings.deployment_mode.value,
        "version": "0.4.2",
        "uptime_seconds": 14 * 86400 + 6 * 3600,
        "scheduler_status": "running",
        "data_dir": "~/.naavik/data",
    }


@router.post("/api/v1/settings/deployment/restart", name="settings_deployment_restart")
async def post_deployment_restart(
    _user: User | None = Depends(require_authed_session),
):
    settings = await sd.get_settings()
    if settings.deployment_mode.value == "cloud":
        raise HTTPException(status_code=405, detail="Restart not allowed on cloud")
    return Response(status_code=202)


@router.get("/api/v1/settings/deployment/logs", name="settings_deployment_logs")
async def get_deployment_logs():
    """SSE stream — emits log lines on a 30s loop."""

    async def gen():
        i = 0
        while i < 12:  # ~12 events then stop (clients reconnect)
            ln = _LOG_LINES_SEED[i % len(_LOG_LINES_SEED)]
            color = {
                "INFO": "text-cyan-400",
                "WARN": "text-amber-400",
                "ERROR": "text-rose-400",
            }.get(ln["level"], "text-slate-300")
            html = (
                '<div class="flex gap-3">'
                f'<span class="text-slate-500 tabular-nums">{ln["timestamp"]}</span>'
                f'<span class="{color} font-medium">{ln["level"]}</span>'
                f'<span class="text-slate-300">{ln["message"]}</span>'
                "</div>"
            )
            yield f"event: logline\ndata: {html}\n\n"
            i += 1
            await asyncio.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/api/v1/settings/account", name="settings_account_get")
async def get_account():
    p = await sd.get_profile()
    return {"full_name": p.full_name, "email": p.email}


@router.put("/api/v1/settings/account", name="settings_account_put")
async def put_account(
    request: Request,
    _user: User | None = Depends(require_authed_session),
):
    return {"ok": True}


@router.put("/api/v1/settings/account/password", name="settings_account_password")
async def put_account_password(
    request: Request,
    fail: Annotated[str | None, Query()] = None,
    _user: User = Depends(require_password_complete),
):
    # Phase 1 stub: real password mutation happens via
    # `POST /api/v1/auth/change-password` in `src/api/auth.py`. Gated with
    # `require_password_complete` so a flagged user can't bypass the must-
    # change flow + complexity check via the Settings · Account form.
    if fail:
        return HTMLResponse(
            '<span class="text-rose-300">Current password incorrect.</span>',
            status_code=422,
        )
    return HTMLResponse('<span class="text-emerald-300">Password updated.</span>')


@router.post("/api/v1/settings/account/delete", name="settings_account_delete")
async def post_account_delete(
    request: Request,
    _user: User | None = Depends(require_authed_session),
):
    return Response(status_code=204)


# ─────────────────────────────────────────────────────────────────────────
# Settings · LLM Provider — `Test connection` fragment route
# Lives at /_fragments/settings/test-connection per BACKEND.md § C.
# ─────────────────────────────────────────────────────────────────────────


@router.post("/_fragments/settings/test-connection", name="settings_test_connection_fragment")
async def post_settings_test_connection_fragment(
    request: Request,
    fail: Annotated[str | None, Query()] = None,
    provider: Annotated[str | None, Query()] = None,  # noqa: ARG001
    _user: User | None = Depends(require_authed_session),
):
    return await post_llm_test(request, fail=fail)


# ─────────────────────────────────────────────────────────────────────────
# Settings · LLM Provider — provider-aware fragment endpoints (plan 10b § 6)
#
# Plan 26 (0.2.0.01): the api-key-field fragment endpoint is DELETED along
# with its template; the LLM tab renders env-presence indicators inline.
# The model-options fragment survives — the model dropdown is still
# provider-dependent.
# ─────────────────────────────────────────────────────────────────────────


_VALID_PROVIDER_IDS = {"anthropic", "openai", "ollama"}


@router.get(
    "/_fragments/settings/llm/model-options",
    name="settings_llm_model_options_fragment",
    response_class=HTMLResponse,
)
async def get_settings_llm_model_options(
    request: Request,
    provider: Annotated[str, Query(min_length=1, max_length=32)],
):
    """Render the model `<select>` for `provider`. Used by HTMX on radio change."""
    if provider not in _VALID_PROVIDER_IDS:
        raise HTTPException(status_code=400, detail="unknown provider")
    settings = await sd.get_settings()
    selected = (
        settings.llm_model
        if (settings and provider == settings.llm_provider.value)
        else _llm_default_model_for(provider)
    )
    return templates.TemplateResponse(
        request,
        "pages/_settings_llm_model_field.html",
        {
            "provider_id": provider,
            "models": _llm_model_options_for(provider),
            "selected": selected,
        },
    )
