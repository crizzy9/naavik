"""Real `/api/v1/settings/*` handlers.

Wave 4 of plan 10 § B.8. Replaces the plan-09 stubs for the state-changing
settings endpoints. Plan-09's HTML page route (`GET /settings`) stays in
`src/ui/routes/settings.py`.

API key for `PUT /api/v1/settings/llm` flows through the vault (never
stored on the Settings row directly).

Plan 10b (item 6, 2026-05-03): `PUT /api/v1/settings/llm` now accepts BOTH
JSON (machine API consumers) and form-encoded (HTMX UI form). The form
path returns a re-rendered `_settings_llm.html` partial with `save_status`
set so the existing form swaps in place via outerHTML.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Request
from sqlmodel.ext.asyncio.session import AsyncSession

# Plan 10b (item 6): the LLM PUT handler intentionally drops `Body()` from
# its signature so an HTMX form-encoded body does not trigger FastAPI's
# JSON parser (which would 422 the request). Body parsing is done inline.
from db.session import get_session
from models import LLMProvider as LLMProviderEnum
from models import User
from services import settings_service
from services.auth import require_authed_session

router = APIRouter()


_FORM_CONTENT_TYPES = (
    "application/x-www-form-urlencoded",
    "multipart/form-data",
)


def _is_form_request(request: Request) -> bool:
    ct = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    return ct in _FORM_CONTENT_TYPES


@router.get("/api/v1/settings/llm", name="api_settings_llm_get")
async def get_llm(session: AsyncSession = Depends(get_session)):
    s = await settings_service.get_or_create(session, user_id=1)
    await session.commit()
    return {
        "llm_provider": s.llm_provider.value,
        "llm_model": s.llm_model,
        "llm_fallback_provider": (
            s.llm_fallback_provider.value if s.llm_fallback_provider else None
        ),
        "llm_api_key_fingerprint": s.llm_api_key_fingerprint,
    }


@router.put("/api/v1/settings/llm", name="api_settings_llm_put")
async def put_llm(
    request: Request,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
):
    """Update LLM provider config.

    Two content types are accepted (plan 10b § 6):
      * `application/x-www-form-urlencoded` (HTMX UI form) → returns the
        re-rendered `pages/_settings_llm.html` partial as HTML.
      * `application/json` (machine consumers) → returns JSON with the
        post-update Settings shape.

    Body is parsed inline — keeping `Body()` in the signature would tempt
    FastAPI to JSON-decode the form payload and 422 the request.
    """
    is_form = _is_form_request(request)
    if is_form:
        form = await request.form()
        # Pydantic / dict semantics: blanks are treated as "no change", not
        # "explicit null", so the operator can leave the API-key field empty
        # to keep the previously-stored value.
        payload = {k: v for k, v in form.items() if str(v).strip()}
    else:
        try:
            payload = await request.json()
        except Exception:  # noqa: BLE001
            payload = {}
        if not isinstance(payload, dict):
            payload = {}

    provider = payload.get("llm_provider")
    fallback_provider = payload.get("llm_fallback_provider")
    api_key = payload.get("api_key") or None
    s = await settings_service.update_llm(
        session,
        user_id=1,
        provider=LLMProviderEnum(provider) if provider else None,
        model=payload.get("llm_model"),
        api_key=api_key,
        fallback_provider=(LLMProviderEnum(fallback_provider) if fallback_provider else None),
    )

    # Form path may also carry the Ollama base URL — store via vault so it
    # survives restarts; the on-row Settings stay secret-free.
    ollama_url = payload.get("ollama_base_url") if is_form else None
    if ollama_url:
        from services import vault as vault_svc

        vault_svc.set(
            "llm",
            "ollama_base_url",
            str(ollama_url),
            caller="settings_llm_form",
        )

    await session.commit()

    if is_form:
        # Re-render the LLM tab fragment with the post-save state. We have
        # to import lazily to avoid the circular `api → ui.routes → api`.
        from ui.routes.settings import _ctx_for_tab
        from ui.templates_setup import templates as ui_templates

        ctx = await _ctx_for_tab(request, "llm-provider")
        ctx["save_status"] = "saved"
        return ui_templates.TemplateResponse(
            request,
            "pages/_settings_llm.html",
            ctx,
        )

    return {
        "llm_provider": s.llm_provider.value,
        "llm_model": s.llm_model,
        "llm_fallback_provider": (
            s.llm_fallback_provider.value if s.llm_fallback_provider else None
        ),
        "llm_api_key_fingerprint": s.llm_api_key_fingerprint,
    }


@router.post("/api/v1/settings/llm/test", name="api_settings_llm_test")
async def post_llm_test(
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
):
    """Try a tiny `provider.complete("ping")` and return ok/latency.

    Wave 4 returns a stub OK without spending a real API call when no
    api_key is configured (avoids surprise costs on first save).
    """
    from llm import get_provider

    s = await settings_service.get_or_create(session, user_id=1)
    if not s.llm_api_key_fingerprint and s.llm_provider.value != "ollama":
        return {"ok": False, "error": "no api_key configured", "model": s.llm_model}

    try:
        provider = get_provider(s)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "model": s.llm_model}

    import time

    t0 = time.perf_counter()
    try:
        result = await provider.complete("ping", max_tokens=8)
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return {
            "ok": True,
            "latency_ms": latency_ms,
            "model": result.model,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "model": s.llm_model}


@router.put("/api/v1/settings/auto-apply", name="api_settings_auto_apply_put")
async def put_auto_apply(
    payload: Annotated[dict[str, Any] | None, Body()] = None,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
):
    payload = payload or {}
    s = await settings_service.update_auto_apply(
        session,
        user_id=1,
        auto_apply_enabled=payload.get("auto_apply_enabled"),
        auto_apply_score_threshold=payload.get("auto_apply_score_threshold"),
        auto_apply_daily_cap=payload.get("auto_apply_daily_cap"),
        eager_review_generation=payload.get("eager_review_generation"),
        daily_llm_cost_cap_usd=payload.get("daily_llm_cost_cap_usd"),
    )
    await session.commit()
    return {
        "auto_apply_enabled": s.auto_apply_enabled,
        "auto_apply_score_threshold": s.auto_apply_score_threshold,
        "auto_apply_daily_cap": s.auto_apply_daily_cap,
        "eager_review_generation": s.eager_review_generation,
        "daily_llm_cost_cap_usd": s.daily_llm_cost_cap_usd,
    }


@router.put("/api/v1/settings/sources", name="api_settings_sources_put")
async def put_sources(
    payload: Annotated[dict[str, Any] | None, Body()] = None,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
):
    payload = payload or {}
    s = await settings_service.update_sources(
        session,
        user_id=1,
        sources_enabled=payload.get("sources_enabled"),
        source_schedules=payload.get("source_schedules"),
        workday_companies=payload.get("workday_companies"),
    )
    await session.commit()
    return {
        "sources_enabled": s.sources_enabled,
        "source_schedules": s.source_schedules,
        "workday_companies": s.workday_companies,
    }


@router.put("/api/v1/settings/notifications", name="api_settings_notifications_put")
async def put_notifications(
    payload: Annotated[dict[str, Any] | None, Body()] = None,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
):
    payload = payload or {}
    s = await settings_service.update_notifications(
        session,
        user_id=1,
        notify_threshold=payload.get("notify_threshold"),
        notify_on_errors=payload.get("notify_on_errors"),
        notifications_enabled=payload.get("notifications_enabled"),
        discord_webhook_url=payload.get("discord_webhook_url"),
        telegram_bot_token=payload.get("telegram_bot_token"),
    )
    await session.commit()
    return {
        "notify_threshold": s.notify_threshold,
        "notify_on_errors": s.notify_on_errors,
        "notifications_enabled": s.notifications_enabled,
        "discord_webhook_configured": s.discord_webhook_configured,
        "telegram_bot_configured": s.telegram_bot_configured,
    }


@router.get("/api/v1/settings/deployment", name="api_settings_deployment_get")
async def get_deployment(session: AsyncSession = Depends(get_session)):
    info = await settings_service.get_deployment_info(session, user_id=1)
    await session.commit()
    return info
