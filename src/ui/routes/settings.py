"""Settings page + tab routes + per-tab JSON / SSE stubs (BACKEND.md § D.7)."""

from __future__ import annotations

import asyncio
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse

from db import sample_data as sd
from ui.templates_setup import templates

router = APIRouter()


_TAB_TEMPLATES: dict[str, str] = {
    "llm-provider": "pages/_settings_llm.html",
    "deployment": "pages/_settings_deployment.html",
    "account": "pages/_settings_account.html",
    "notifications": "pages/_settings_notifications.html",
    "auto-apply": "pages/_settings_auto_apply.html",
    "sources": "pages/_settings_sources.html",
}

_VALID_TABS = set(_TAB_TEMPLATES.keys())


_PROVIDERS_DISPLAY = [
    {
        "id": "anthropic",
        "name": "Anthropic Claude",
        "model_default": "claude-3.5-sonnet-20250219",
        "description": "Recommended · best resume bullet quality.",
        "kind": "CLOUD",
    },
    {
        "id": "openai",
        "name": "OpenAI GPT",
        "model_default": "gpt-4o",
        "description": "Faster, slightly cheaper.",
        "kind": "CLOUD",
    },
    {
        "id": "ollama",
        "name": "Ollama (Local)",
        "model_default": "llama3.1:70b",
        "description": "Llama 3.1 70B on your machine · private.",
        "kind": "LOCAL",
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

_LLM_API_KEY_PLACEHOLDERS: dict[str, str] = {
    "anthropic": "sk-ant-…",
    "openai": "sk-…",
    "ollama": "",
}


def _llm_model_options_for(provider_id: str) -> list[str]:
    return list(_LLM_MODEL_OPTIONS.get(provider_id, []))


def _llm_default_model_for(provider_id: str) -> str:
    options = _LLM_MODEL_OPTIONS.get(provider_id, [])
    return options[0] if options else ""


def _llm_api_key_field_ctx(provider_id: str, settings) -> dict[str, object]:
    """Build the context for `_settings_llm_api_key_field.html` for one provider.

    `has_existing_key` is True only when the active provider matches AND
    the Settings row carries a fingerprint — gives the operator a "key
    already saved, leave blank to keep it" hint without leaking the value.
    """
    has_existing_key = bool(
        settings is not None
        and provider_id == getattr(settings.llm_provider, "value", None)
        and getattr(settings, "llm_api_key_fingerprint", None)
    )
    ollama_base_url: str | None = None
    if provider_id == "ollama":
        try:
            from services import vault as vault_svc

            ollama_base_url = vault_svc.get(
                "llm",
                "ollama_base_url",
                caller="settings_llm_form",
            )
        except Exception:  # noqa: BLE001
            ollama_base_url = None
    return {
        "provider_id": provider_id,
        "placeholder": _LLM_API_KEY_PLACEHOLDERS.get(provider_id, ""),
        "has_existing_key": has_existing_key,
        "ollama_base_url": ollama_base_url,
    }


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


_ON_DISK = [
    {
        "label": "DATA DIR",
        "path": "~/.naavik/data",
        "sub": "412 MB · 27 jobs · 14 applications",
        "icon": "folder",
    },
    {
        "label": "SECRETS",
        "path": "~/.naavik/secrets.enc",
        "sub": "aes-256-gcm · 4 keys",
        "icon": "lock",
    },
    {
        "label": "CONFIG",
        "path": "~/.naavik/config.toml",
        "sub": "last edited 2d ago",
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


async def _ctx_for_tab(request: Request, tab: str) -> dict[str, object]:
    if tab not in _VALID_TABS:
        raise HTTPException(status_code=404, detail="Unknown settings tab")
    settings = await sd.get_settings()
    cost_summary = await sd.llm_usage_summary(days=30)
    provider_id = settings.llm_provider.value if settings else "anthropic"
    deployment_info = await _deployment_render_info(settings)

    return {
        "current_tab": tab,
        "tab_template": _TAB_TEMPLATES[tab],
        "settings": settings,
        "profile": await sd.get_profile(),
        "providers": _PROVIDERS_DISPLAY,
        "cost_summary": cost_summary,
        # Plan 10b (item 6): LLM tab fragment context — the form template
        # resolves model + api-key field state from these. The fragment
        # endpoints below build the same context for HTMX swaps.
        "provider_id": provider_id,
        "model_options": _llm_model_options_for(provider_id),
        "selected_model": settings.llm_model or _llm_default_model_for(provider_id),
        "api_key_field": _llm_api_key_field_ctx(provider_id, settings),
        "save_status": None,
        # Deployment tab context — augmented with vault status (item 7).
        "deployment": deployment_info,
        "log_lines": _LOG_LINES_SEED,
        "on_disk": _ON_DISK,
        "active_sidebar": "settings",
        "active_template_path": "/settings/:tab" if tab != "llm-provider" else "/settings",
    }


async def _deployment_render_info(settings) -> dict[str, object]:
    """Build the `deployment` ctx dict consumed by `_settings_deployment.html`.

    Plan 10b (item 7, 2026-05-03): adds `vault_locked`,
    `vault_fingerprint_stored`, and `vault_fingerprint_expected` so the
    template can render the rose vault-locked banner when SECRET_KEY drifts
    from the value used to encrypt the on-disk vault.
    """
    from services import vault as vault_svc

    try:
        stored = vault_svc.fingerprint()
    except Exception:  # noqa: BLE001
        stored = None
    try:
        expected = vault_svc.expected_fingerprint()
    except Exception:  # noqa: BLE001
        expected = None
    try:
        locked = vault_svc.is_locked()
    except Exception:  # noqa: BLE001
        locked = False

    mode_value = settings.deployment_mode.value if settings else "self_hosted"
    return {
        "mode": "self-hosted" if mode_value == "self_hosted" else "cloud",
        "status": "active",
        "version": "0.4.2",
        "meta": "docker-compose · uptime 14d 6h · last restart Apr 14",
        "update_available_version": "0.4.3",
        "vault_locked": bool(locked),
        "vault_fingerprint_stored": stored,
        "vault_fingerprint_expected": expected,
    }


@router.get("/settings", response_class=HTMLResponse, name="settings")
async def get_settings(request: Request):
    ctx = await _ctx_for_tab(request, "llm-provider")
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

    Returns an HTML card; the upstream button (in `_settings_llm_api_key_field.html`)
    swaps the result into `#llm-test-result`. JSON-style probe of the live
    provider lives in `src/api/settings.py:post_llm_test` under the same
    path; the form's button calls the fragment route below, not the API.
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
async def put_auto_apply(request: Request):
    return {"ok": True}


@router.put("/api/v1/settings/sources", name="settings_sources_put")
async def put_sources(request: Request):
    return {"ok": True}


@router.put("/api/v1/settings/notifications", name="settings_notifications_put")
async def put_notifications(request: Request):
    return {"ok": True}


@router.post("/api/v1/settings/notifications/test", name="settings_notifications_test")
async def post_notifications_test(
    request: Request,
    channel: Annotated[Literal["discord", "telegram"], Query()],
    fail: Annotated[str | None, Query()] = None,
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
async def post_deployment_restart():
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
async def put_account(request: Request):
    return {"ok": True}


@router.put("/api/v1/settings/account/password", name="settings_account_password")
async def put_account_password(
    request: Request,
    fail: Annotated[str | None, Query()] = None,
):
    if fail:
        return HTMLResponse(
            '<span class="text-rose-300">Current password incorrect.</span>',
            status_code=422,
        )
    return HTMLResponse('<span class="text-emerald-300">Password updated.</span>')


@router.post("/api/v1/settings/account/delete", name="settings_account_delete")
async def post_account_delete(request: Request):
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
):
    return await post_llm_test(request, fail=fail)


# ─────────────────────────────────────────────────────────────────────────
# Settings · LLM Provider — provider-aware fragment endpoints (plan 10b § 6)
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


@router.get(
    "/_fragments/settings/llm/api-key-field",
    name="settings_llm_api_key_field_fragment",
    response_class=HTMLResponse,
)
async def get_settings_llm_api_key_field(
    request: Request,
    provider: Annotated[str, Query(min_length=1, max_length=32)],
):
    """Render the API-key (or Ollama base URL) input for `provider`."""
    if provider not in _VALID_PROVIDER_IDS:
        raise HTTPException(status_code=400, detail="unknown provider")
    settings = await sd.get_settings()
    ctx = _llm_api_key_field_ctx(provider, settings)
    return templates.TemplateResponse(
        request,
        "pages/_settings_llm_api_key_field.html",
        ctx,
    )
