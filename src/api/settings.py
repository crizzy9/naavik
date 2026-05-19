"""Real `/api/v1/settings/*` handlers.

Wave 4 of plan 10 § B.8. Replaces the plan-09 stubs for the state-changing
settings endpoints. Plan-09's HTML page route (`GET /settings`) stays in
`src/ui/routes/settings.py`.

Plan 26 (0.2.0.01): the encrypted vault is gone. API keys, webhook URLs,
and bot tokens are configured via env vars in `.env` (read by
`pydantic-settings` in `src/config.py`). `PUT /api/v1/settings/llm` and
`PUT /api/v1/settings/notifications` now reject any payload carrying
secret material with a 422 + explicit guidance. `GET` responses expose
env-derived presence indicators (bools), never values.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import JSONResponse
from sqlmodel.ext.asyncio.session import AsyncSession

# Plan 10b (item 6): the LLM PUT handler intentionally drops `Body()` from
# its signature so an HTMX form-encoded body does not trigger FastAPI's
# JSON parser (which would 422 the request). Body parsing is done inline.
from db.session import get_session
from models import LLMProvider as LLMProviderEnum
from models import User
from services import env_secrets, settings_service
from services.auth import require_authed_session

router = APIRouter()


_FORM_CONTENT_TYPES = (
    "application/x-www-form-urlencoded",
    "multipart/form-data",
)


def _is_form_request(request: Request) -> bool:
    ct = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    return ct in _FORM_CONTENT_TYPES


def _llm_response_payload(s) -> dict[str, Any]:
    return {
        "llm_provider": s.llm_provider.value,
        "llm_model": s.llm_model,
        "llm_fallback_provider": (
            s.llm_fallback_provider.value if s.llm_fallback_provider else None
        ),
        "env_indicators": env_secrets.env_indicators_for_llm_tab(),
    }


def _notifications_response_payload(s) -> dict[str, Any]:
    return {
        "notify_threshold": s.notify_threshold,
        "notify_on_errors": s.notify_on_errors,
        "notifications_enabled": s.notifications_enabled,
        "env_indicators": env_secrets.env_indicators_for_notifications_tab(),
    }


@router.get("/api/v1/settings/llm", name="api_settings_llm_get")
async def get_llm(session: AsyncSession = Depends(get_session)):
    s = await settings_service.get_or_create(session, user_id=1)
    await session.commit()
    return _llm_response_payload(s)


@router.put("/api/v1/settings/llm", name="api_settings_llm_put")
async def put_llm(
    request: Request,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
):
    """Update LLM provider config.

    Two content types accepted (plan 10b § 6):
      * `application/x-www-form-urlencoded` (HTMX UI form) → returns the
        re-rendered `pages/_settings_llm.html` partial as HTML.
      * `application/json` (machine consumers) → returns JSON with the
        post-update Settings shape.

    Plan 26 (0.2.0.01): rejects any payload carrying `api_key` or
    `ollama_base_url` with a 422 + clear migration message. Values are
    env-only post-vault.
    """
    is_form = _is_form_request(request)
    if is_form:
        form = await request.form()
        payload = {k: v for k, v in form.items() if str(v).strip()}
    else:
        try:
            payload = await request.json()
        except Exception:  # noqa: BLE001
            payload = {}
        if not isinstance(payload, dict):
            payload = {}

    if payload.get("api_key") or payload.get("ollama_base_url"):
        return JSONResponse(
            status_code=422,
            content={
                "detail": (
                    "API keys + Ollama base URL are configured via env vars "
                    "(ANTHROPIC_API_KEY / OPENAI_API_KEY / OLLAMA_BASE_URL) "
                    "starting in 0.2.0. Edit .env and restart. "
                    "See README § Configuration."
                ),
            },
        )

    provider = payload.get("llm_provider")
    fallback_provider = payload.get("llm_fallback_provider")
    s = await settings_service.update_llm(
        session,
        user_id=1,
        provider=LLMProviderEnum(provider) if provider else None,
        model=payload.get("llm_model"),
        fallback_provider=(LLMProviderEnum(fallback_provider) if fallback_provider else None),
    )
    await session.commit()

    if is_form:
        from ui.routes.settings import _ctx_for_tab
        from ui.templates_setup import templates as ui_templates

        ctx = await _ctx_for_tab(request, "llm-provider")
        ctx["save_status"] = "saved"
        return ui_templates.TemplateResponse(
            request,
            "pages/_settings_llm.html",
            ctx,
        )

    return _llm_response_payload(s)


@router.post("/api/v1/settings/llm/test", name="api_settings_llm_test")
async def post_llm_test(
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
):
    """Try a tiny `provider.complete("ping")` and return ok/latency.

    Plan 26 (0.2.0.01): the "no api_key configured" guard now consults
    env-presence indicators instead of `Settings.llm_api_key_fingerprint`.
    """
    from llm import get_provider

    s = await settings_service.get_or_create(session, user_id=1)
    if not env_secrets.llm_provider_configured(s.llm_provider) and s.llm_provider.value != "ollama":
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
    """Update notification preferences.

    Plan 26 (0.2.0.01): rejects any payload carrying `discord_webhook_url`
    or `telegram_bot_token` with a 422 + env-migration guidance. Webhook
    URL and bot token + chat ID are env-only post-vault.
    """
    payload = payload or {}
    if payload.get("discord_webhook_url") or payload.get("telegram_bot_token"):
        return JSONResponse(
            status_code=422,
            content={
                "detail": (
                    "Discord webhook URL + Telegram bot token are configured "
                    "via env vars (DISCORD_WEBHOOK_URL / TELEGRAM_BOT_TOKEN / "
                    "TELEGRAM_CHAT_ID) starting in 0.2.0. Edit .env and "
                    "restart. See README § Configuration."
                ),
            },
        )

    s = await settings_service.update_notifications(
        session,
        user_id=1,
        notify_threshold=payload.get("notify_threshold"),
        notify_on_errors=payload.get("notify_on_errors"),
        notifications_enabled=payload.get("notifications_enabled"),
    )
    await session.commit()
    return _notifications_response_payload(s)


@router.get("/api/v1/settings/deployment", name="api_settings_deployment_get")
async def get_deployment(session: AsyncSession = Depends(get_session)):
    info = await settings_service.get_deployment_info(session, user_id=1)
    await session.commit()
    return info
