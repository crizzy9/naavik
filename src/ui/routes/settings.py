"""Settings page + tab routes + per-tab JSON / SSE stubs (BACKEND.md § D.7).

Plan 26 (0.2.0.01): the encrypted vault is gone. The API-key fragment
endpoint (`/_fragments/settings/llm/api-key-field`) is deleted along with
its template; the LLM tab now renders env-presence indicators instead of
an input. Deployment-tab context drops the vault-locked banner triplet.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from api.auth import _set_session_cookies, require_csrf
from config import settings as app_settings
from db.session import get_session
from models import JobScrapeRunRead, JobSource, User
from services import (
    account_service,
    application_service,
    env_secrets,
    job_service,
    llm_tracker,
    profile_service,
    settings_service,
)
from services.auth import (
    SESSION_COOKIE,
    hash_password_with_complexity_check,
    issue_csrf_token,
    issue_jwt_async,
    require_authed_session,
    require_password_complete,
    revoke_jwt,
    verify_jwt_async,
    verify_password,
)
from ui.templates_setup import templates

router = APIRouter()


_TAB_TEMPLATES: dict[str, str] = {
    "llm-provider": "pages/_settings_llm.html",
    "generation": "pages/_settings_generation.html",
    "deployment": "pages/_settings_deployment.html",
    "account": "pages/_settings_account.html",
    "notifications": "pages/_settings_notifications.html",
    "auto-apply": "pages/_settings_auto_apply.html",
    "sources": "pages/_settings_sources.html",
    "submissions": "pages/_settings_submissions.html",
    "security": "pages/_settings_security.html",
}

_VALID_TABS = set(_TAB_TEMPLATES.keys())


# 0.7.0.48 W4 — common Save button. Each writable tab maps to the canonical
# bulk-PUT endpoint the shared header button submits to via the form= attr.
# `None` hides the button (read-only tabs OR tabs whose only mutation is a
# dedicated sub-action like "Rotate JWT key").
_SAVE_ENDPOINT_FOR_TAB: dict[str, str | None] = {
    "account": "/api/v1/settings/account",
    "llm-provider": "/api/v1/settings/llm",
    "generation": "/api/v1/settings/generation",
    "notifications": "/api/v1/settings/notifications",
    "auto-apply": "/api/v1/settings/auto-apply",
    "sources": None,
    "submissions": None,
    "security": None,
    "deployment": None,
}


_PROVIDERS_DISPLAY = [
    {
        "id": "anthropic",
        "name": "Anthropic Claude",
        "model_default": "claude-sonnet-4-6",
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
        "claude-opus-4-8",
        "claude-sonnet-4-6",
        "claude-haiku-4-5",
    ],
    "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
    "ollama": ["llama3.1:70b", "llama3.1:8b", "qwen2.5:32b"],
}


def _llm_model_options_for(provider_id: str) -> list[str]:
    return list(_LLM_MODEL_OPTIONS.get(provider_id, []))


def _llm_default_model_for(provider_id: str) -> str:
    options = _LLM_MODEL_OPTIONS.get(provider_id, [])
    return options[0] if options else ""


# Deployment-tab log tail was a hardcoded fake-activity seed (0.7.0-era stub).
# Removed: self-hosters read real logs via `docker compose logs -f naavik`
# (Docker) or `journalctl -u naavik -f` (NixOS). The template now links to
# those instead of streaming a fabricated feed.


def _dir_size_human(path: Path) -> str:
    """Best-effort human-readable total size of `path` (empty string on error)."""
    try:
        total = float(sum(f.stat().st_size for f in path.glob("**/*") if f.is_file()))
    except OSError:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if total < 1024 or unit == "GB":
            return f"{total:.0f} {unit}"
        total /= 1024
    return ""


async def _on_disk_view(session: AsyncSession | None, *, user_id: int) -> list[dict[str, object]]:
    """Real on-disk footprint for the Deployment tab.

    Replaces the hardcoded "412 MB · 27 jobs · 14 applications" fixture with
    live counts (jobs + applications for the user) and the actual configured
    data directory + its real size.
    """
    from pathlib import Path as _Path

    data_dir = _Path(app_settings.data_dir)
    job_count = app_count = 0
    if session is not None:
        # Graceful degrade: a session double without a live `.exec` (test
        # NoopSession) falls back to zero counts rather than crashing the tab.
        try:
            from sqlmodel import func, select

            from models import Application, Job

            job_count = int(
                (
                    await session.exec(
                        select(func.count(Job.id)).where(
                            Job.user_id == user_id, Job.deleted_at.is_(None)
                        )
                    )
                ).one()
                or 0
            )
            app_count = int(
                (
                    await session.exec(
                        select(func.count(Application.id)).where(
                            Application.user_id == user_id, Application.deleted_at.is_(None)
                        )
                    )
                ).one()
                or 0
            )
        except Exception:  # noqa: BLE001 — degrade, never 500 the tab
            job_count = app_count = 0

    size_label = _dir_size_human(data_dir) if data_dir.exists() else "not created yet"
    return [
        {
            "label": "DATA DIR",
            "path": str(data_dir),
            "sub": f"{size_label} · {job_count} jobs · {app_count} applications",
            "icon": "folder",
        },
        {
            "label": "CONFIG",
            "path": ".env",
            "sub": "env-loaded · gitignored",
            "icon": "file-cog",
        },
        {
            "label": "UPLOADS",
            "path": str(data_dir / "uploads"),
            "sub": "resume PDFs (per-user)",
            "icon": "file-text",
        },
    ]


# ─────────────────────────────────────────────────────────────────────────
# Page handlers
# ─────────────────────────────────────────────────────────────────────────


async def _ctx_for_tab(
    request: Request,
    tab: str,
    *,
    session: AsyncSession,
    user_id: int = 1,
) -> dict[str, object]:
    if tab not in _VALID_TABS:
        raise HTTPException(status_code=404, detail="Unknown settings tab")
    settings = await settings_service.get_or_create(session, user_id=user_id)
    cost_summary = await llm_tracker.usage_summary(session, user_id=user_id, days=30)
    profile = await profile_service.get_profile(session, user_id)
    saved_provider_id = settings.llm_provider.value if settings else "anthropic"
    env_indicators = env_secrets.env_indicators_for_llm_tab()
    active_provider = env_secrets.resolve_active_llm_provider()
    # 0.7.0.48 fold-in: when the saved preference's env key is absent but
    # a different provider IS env-configured, the factory falls back to the
    # env-resolved active. Mirror that in the model dropdown so the operator
    # sees the model catalog for the provider that LLM calls will actually
    # use — otherwise the dropdown lists e.g. Anthropic models while calls
    # route through OpenAI, which is the same surface confusion the mismatch
    # banner warns about. `saved_provider_id` is preserved for the mismatch
    # banner detection in the template.
    pref_has_env = env_indicators.get(saved_provider_id, False)
    provider_id = saved_provider_id if pref_has_env or active_provider is None else active_provider
    deployment_info = await _deployment_render_info(settings)

    ctx: dict[str, object] = {
        "current_tab": tab,
        "tab_template": _TAB_TEMPLATES[tab],
        "active_save_endpoint": _SAVE_ENDPOINT_FOR_TAB.get(tab),
        "save_form_id": "settings-active-form",
        "settings": settings,
        "profile": profile,
        "providers": _PROVIDERS_DISPLAY,
        "cost_summary": cost_summary,
        # Plan 10b (item 6): LLM tab fragment context — the form template
        # resolves model + env-indicator state from these. The model fragment
        # endpoint below builds the same context for HTMX swaps.
        "provider_id": provider_id,
        "saved_provider_id": saved_provider_id,
        "model_options": _llm_model_options_for(provider_id),
        # Select the SAVED model whenever it belongs to the rendered
        # provider's catalog. Comparing provider ids instead used to drop
        # the user's saved choice on every reload when the preference
        # provider (no env key) differed from the env-active one — Save
        # said "Saved" but the dropdown silently reverted.
        "selected_model": (
            settings.llm_model
            if settings and settings.llm_model in _llm_model_options_for(provider_id)
            else _llm_default_model_for(provider_id)
        ),
        "env_indicators": env_indicators,
        "notify_env_indicators": env_secrets.env_indicators_for_notifications_tab(),
        # Plan 70 (0.3.3.13): single env-resolved active-provider label.
        # Replaces the deleted "Active provider" radio surface — no UI
        # mutation; precedence ANTHROPIC > OPENAI > OLLAMA.
        "active_provider": active_provider,
        "save_status": None,
        "deployment": deployment_info,
        "active_sidebar": "settings",
        "active_template_path": "/settings/:tab" if tab != "llm-provider" else "/settings",
    }

    if tab == "deployment":
        ctx["on_disk"] = await _on_disk_view(session, user_id=user_id)

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
        # Plan 74 / 0.3.2.04 — judge-skipped fallback banner.
        if session is None:
            ctx["judge_skipped_count_today"] = 0
            ctx["judge_skipped_reasons_today"] = {}
        else:
            ctx["judge_skipped_count_today"] = await llm_tracker.judge_skipped_count_today(
                session, user_id=user_id
            )
            ctx["judge_skipped_reasons_today"] = await llm_tracker.judge_skipped_reasons_today(
                session, user_id=user_id
            )

    if tab == "security":
        ctx["security"] = await _build_security_view(session, user_id=user_id)

    if tab == "generation":
        ctx["cost_projection"] = await _build_generation_cost_projection(session, user_id=user_id)
        ctx["recent_generation_traces"] = await _build_recent_generation_traces(
            session, user_id=user_id
        )

    return ctx


# ── Settings · Generation context (plan 67 / 0.3.4 § C.6) ────────────────


async def _build_generation_cost_projection(session: AsyncSession | None, *, user_id: int):
    """Return CostProjection for the Generation tab. Falls back to ROADMAP
    estimates when session-less or query fails."""
    if session is None:
        from services.settings_service import _PREMIUM_PROJECTION_FALLBACK

        return _PREMIUM_PROJECTION_FALLBACK
    return await settings_service.compute_premium_cost_projection(session, user_id=user_id)


async def _build_recent_generation_traces(
    session: AsyncSession | None, *, user_id: int
) -> list[dict]:
    """Return the last 20 Applications with non-null generation_trace."""
    if session is None:
        return []
    return await settings_service.list_recent_generation_traces(session, user_id=user_id, limit=20)


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
        # Plan 64 / 0.2.7.11 — LinkedIn proxy presence indicator. The host is
        # rendered (not the userinfo) so operators can verify which provider
        # they configured without exposing credentials. None for non-LinkedIn
        # sources; the multi-source generalization lands in 0.8.0.NN.
        proxy_view: dict[str, object] | None = None
        if source is JobSource.LINKEDIN:
            proxy_view = {
                "configured": env_secrets.linkedin_proxy_configured(),
                "host": env_secrets.linkedin_proxy_host_redacted(),
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
                "proxy": proxy_view,
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


def _app_version() -> str:
    """Resolve the real installed package version (falls back to pyproject)."""
    try:
        from importlib.metadata import PackageNotFoundError, version

        try:
            return version("naavik")
        except PackageNotFoundError:
            return "dev"
    except Exception:  # noqa: BLE001
        return "dev"


async def _deployment_render_info(settings) -> dict[str, object]:
    """Build the `deployment` ctx dict consumed by `_settings_deployment.html`.

    Plan 26 (0.2.0.01): vault status fields removed.

    Hardening pass: previously returned hardcoded uptime ("14d 6h"), a fake
    "last restart Apr 14", and a fake "update available v0.4.3" that rendered a
    non-functional Update button. Now reports only real, verifiable facts:
    deployment mode, the actual package version, whether the scheduler is
    running, and the configured data directory. No fake update prompt.
    """
    mode_value = settings.deployment_mode.value if settings else "self_hosted"
    scheduler_running = False
    try:
        from scheduler import is_running as _sched_running

        scheduler_running = bool(_sched_running())
    except Exception:  # noqa: BLE001 — scheduler optional
        scheduler_running = False
    return {
        "mode": "self-hosted" if mode_value == "self_hosted" else "cloud",
        "status": "active",
        "version": _app_version(),
        "meta": (
            f"{'scheduler running' if scheduler_running else 'scheduler stopped'}"
            f" · data dir {app_settings.data_dir}"
        ),
        "update_available_version": None,
        "scheduler_running": scheduler_running,
    }


@router.get("/settings", response_class=HTMLResponse, name="settings")
async def get_settings(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    ctx = await _ctx_for_tab(
        request, "llm-provider", session=session, user_id=_effective_user_id(user)
    )
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
    return templates.TemplateResponse(request, "pages/settings.html", ctx)


_MANUAL_RUN_MAX_LISTINGS = 10


@router.post(
    "/_fragments/settings/sources/{source}/run",
    response_class=HTMLResponse,
    name="settings_source_run_fragment",
)
async def post_settings_source_run(
    request: Request,
    source: str,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    """Queue a one-off bounded scrape for `source`, scoped to the caller.

    Manual verification path for local dev + self-hosters: schedules a
    transient DateTrigger(now) run of the source's cron body capped at
    `_MANUAL_RUN_MAX_LISTINGS` listings for the requesting user only.
    Returns an inline status chip (swapped over the button); the run's
    outcome lands in the "Recent scraper runs" table on refresh.
    """
    from datetime import UTC, datetime
    from uuid import uuid4

    from apscheduler.triggers.date import DateTrigger

    from scheduler import get_scheduler
    from scraper.sites import scrapers as scraper_registry

    def _chip(tone: str, icon: str, text: str, status_code: int = 200) -> HTMLResponse:
        tones = {
            "emerald": "bg-emerald-500/15 text-emerald-200 ring-emerald-500/30",
            "rose": "bg-rose-500/15 text-rose-200 ring-rose-500/30",
        }
        return HTMLResponse(
            f'<span data-source-run-result="{tone}" class="inline-flex items-center '
            f'gap-1 px-2 py-1 rounded text-[11px] font-mono ring-1 {tones[tone]}">'
            f'<i data-lucide="{icon}" class="h-3 w-3" stroke-width="1.5"></i>'
            f"{text}</span>",
            status_code=status_code,
        )

    if source not in scraper_registry:
        return _chip("rose", "circle-alert", "unknown source", 404)

    user_id = _effective_user_id(user)
    user_settings = await settings_service.get_or_create(session, user_id=user_id)
    if not env_secrets.scraper_source_configured(JobSource(source), user_settings):
        hint = (
            "set keywords via Configure"
            if source in ("linkedin", "indeed")
            else "set its company list first (see Configure)"
        )
        return _chip("rose", "circle-alert", f"not configured — {hint}", 422)

    scheduler = get_scheduler()
    if scheduler is None:
        return _chip("rose", "circle-alert", "scheduler not running", 503)
    job = scheduler.get_job(f"scraping.{source}")
    if job is None:
        return _chip("rose", "circle-alert", "scrape job not registered", 503)

    manual_id = f"scraping.{source}-manual-{uuid4().hex[:8]}"
    scheduler.add_job(
        job.func,
        DateTrigger(run_date=datetime.now(UTC)),
        id=manual_id,
        name=manual_id,
        kwargs={
            "max_listings": _MANUAL_RUN_MAX_LISTINGS,
            "only_user_id": _effective_user_id(user),
        },
        max_instances=1,
        coalesce=True,
        replace_existing=False,
    )
    return _chip("emerald", "check", "queued — see Recent scraper runs")


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
    return templates.TemplateResponse(request, "pages/settings.html", ctx)


@router.get("/settings/generation", response_class=HTMLResponse, name="settings_generation")
async def get_settings_generation(
    request: Request,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
):
    """Settings · Generation sub-tab — plan 67 (0.3.4) § C.6.

    Carries tier toggle (FREE / PREMIUM), per-app cost projection,
    TIER-2 evasion opt-in, Originality.ai API key, audit-trail viewer.
    Gated by `require_authed_session`; `Depends(get_session)` so the
    cost-projection query + audit-trail query can hit the DB.
    """
    ctx = await _ctx_for_tab(
        request, "generation", session=session, user_id=_effective_user_id(_user)
    )
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
    return templates.TemplateResponse(request, "pages/settings.html", ctx)


@router.get("/settings/{tab}", response_class=HTMLResponse, name="settings_tab")
async def get_settings_tab(
    request: Request,
    tab: str,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    if tab not in _VALID_TABS:
        raise HTTPException(status_code=404, detail="Unknown settings tab")
    ctx = await _ctx_for_tab(request, tab, session=session, user_id=_effective_user_id(user))
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
        {"ok": True, "latency_ms": 412, "model": "claude-sonnet-4-6"},
    )


@router.get("/api/v1/settings/llm/usage", name="settings_llm_usage")
async def get_llm_usage(
    period: Annotated[str, Query()] = "month",
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    summary = await llm_tracker.usage_summary(
        session,
        user_id=_effective_user_id(user),
        days=30 if period == "month" else 7,
    )
    return {
        "month_cost_usd": summary.month_cost_usd,
        "avg_per_generation_usd": summary.avg_per_generation_usd,
        "total_tokens": summary.total_tokens,
        "gen_count": summary.gen_count,
    }


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
    user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    """Send a REAL test message to the configured Discord/Telegram channel.

    Was a stub that reported success without sending anything. Now dispatches
    an actual message via `services.notifications` and reports the true
    outcome — including an honest "not configured" message when the channel's
    env var is unset.
    """
    from services import notifications

    if channel == "discord" and not app_settings.discord_webhook_url:
        return HTMLResponse(
            '<span class="text-amber-300">DISCORD_WEBHOOK_URL not set in .env.</span>',
            status_code=422,
        )
    if channel == "telegram" and not (
        app_settings.telegram_bot_token and app_settings.telegram_chat_id
    ):
        return HTMLResponse(
            '<span class="text-amber-300">TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set '
            "in .env.</span>",
            status_code=422,
        )

    ok = await notifications.send_test_message(channel=channel)
    if ok:
        return HTMLResponse(f'<span class="text-emerald-300">Sent a test {channel} message.</span>')
    return HTMLResponse(
        f'<span class="text-rose-300">Couldn\'t reach {channel} — check the '
        "webhook/token and Naavik logs.</span>",
        status_code=502,
    )


@router.get("/api/v1/settings/deployment", name="settings_deployment_get")
async def get_deployment(
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    settings = await settings_service.get_or_create(session, user_id=_effective_user_id(user))
    scheduler_running = False
    try:
        from scheduler import is_running as _sched_running

        scheduler_running = bool(_sched_running())
    except Exception:  # noqa: BLE001
        scheduler_running = False
    return {
        "mode": settings.deployment_mode.value,
        "version": _app_version(),
        "scheduler_status": "running" if scheduler_running else "stopped",
        "data_dir": app_settings.data_dir,
    }


# The fake in-app "Restart" endpoint (returned 202 without restarting) and the
# fabricated log-stream SSE endpoint were removed in the hardening pass. Process
# lifecycle is owned by the supervisor (Docker / systemd); logs are read there.


@router.get("/api/v1/settings/account", name="settings_account_get")
async def get_account(
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    p = await profile_service.get_profile(session, _effective_user_id(user))
    if p is None:
        raise HTTPException(status_code=404, detail="Profile not found")
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
    user: User = Depends(require_password_complete),
    session: AsyncSession = Depends(get_session),
    naavik_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
    _csrf: None = Depends(require_csrf),
):
    """Change the account password from Settings · Account.

    Was a stub that always returned "Password updated." without touching the
    DB (a fake-success state). Now performs the real mutation: re-verify the
    current password, complexity-check the new one, rotate the bcrypt hash,
    revoke the presenting JWT, and re-issue session + CSRF cookies. Returns an
    inline `#account-password-result` fragment (kept on the Settings page)
    rather than the login-card redirect the `/api/v1/auth/change-password`
    endpoint emits.
    """
    form = await request.form()
    current = str(form.get("current") or "")
    new = str(form.get("new") or "")

    if not current or not new:
        return HTMLResponse(
            '<span class="text-rose-300">Current and new passwords are required.</span>',
            status_code=422,
        )
    if not verify_password(current, user.password_hash):
        return HTMLResponse(
            '<span class="text-rose-300">Current password is incorrect.</span>',
            status_code=422,
        )
    if new == current:
        return HTMLResponse(
            '<span class="text-rose-300">New password must differ from the current one.</span>',
            status_code=422,
        )
    try:
        new_hash = hash_password_with_complexity_check(new)
    except ValueError as exc:
        safe = str(exc).replace("<", "&lt;").replace(">", "&gt;")
        return HTMLResponse(f'<span class="text-rose-300">{safe}</span>', status_code=422)

    # Revoke the presenting JWT so the pre-rotation cookie can't be replayed.
    if naavik_session:
        result = await verify_jwt_async(session, naavik_session)
        if result is not None:
            old_user_id, old_jti, old_exp = result
            await revoke_jwt(session, jti=old_jti, user_id=old_user_id, expires_at=old_exp)

    user.password_hash = new_hash
    user.must_change_password = False
    session.add(user)
    await session.commit()

    secure = not request.app.debug if hasattr(request.app, "debug") else True
    jwt_value = await issue_jwt_async(session, user_id=user.id, keep_signed_in=False)
    csrf_value = issue_csrf_token()
    response = HTMLResponse('<span class="text-emerald-300">Password updated.</span>')
    _set_session_cookies(
        response,
        jwt_value=jwt_value,
        csrf_value=csrf_value,
        keep_signed_in=False,
        secure=secure,
    )
    return response


@router.post("/api/v1/settings/account/delete", name="settings_account_delete")
async def post_account_delete(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_password_complete),
    _csrf: None = Depends(require_csrf),
):
    """Permanently delete the account and every owned row.

    Was a stub returning 204 without deleting anything (fake-success). Now
    hard-deletes via `account_service.delete_user_account`, revokes the
    presenting JWT, clears the session cookies, and redirects to /login.

    Gated with `require_password_complete` (real JWT required) + CSRF — a
    destructive, irreversible action must never run on the dev fake session.
    """
    deleted = await account_service.delete_user_account(session, user_id=user.id)
    if not deleted:
        await session.rollback()
        raise HTTPException(status_code=404, detail="Account not found")
    await session.commit()

    # No explicit JWT revocation needed: the user row (and its revoked_jwt
    # rows) are gone, so any replay of the old cookie fails the `get_user_by_id`
    # lookup in `get_current_user` and is rejected with 401.
    response = Response(status_code=204)
    response.headers["HX-Redirect"] = "/login"
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie("naavik_csrf", path="/")
    return response


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
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    """Render the model `<select>` for `provider`. Used by HTMX on radio change."""
    if provider not in _VALID_PROVIDER_IDS:
        raise HTTPException(status_code=400, detail="unknown provider")
    settings = await settings_service.get_or_create(session, user_id=_effective_user_id(user))
    selected = (
        settings.llm_model
        if (settings and settings.llm_model in _llm_model_options_for(provider))
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
