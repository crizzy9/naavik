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
from pydantic import ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession

# Plan 10b (item 6): the LLM PUT handler intentionally drops `Body()` from
# its signature so an HTMX form-encoded body does not trigger FastAPI's
# JSON parser (which would 422 the request). Body parsing is done inline.
from api.auth import require_csrf
from db.session import get_session
from models import JobSource, User
from models import LLMProvider as LLMProviderEnum
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
    # Plan 61 (0.2.7.16) — checkbox tri-state idiom mirrors plan 59 / 0.2.7.12.
    # Absent key = skip; present truthy/falsy = set bool(value).
    semantic_enabled_raw = payload.get("semantic_match_enabled")
    semantic_enabled = bool(semantic_enabled_raw) if "semantic_match_enabled" in payload else None
    semantic_sync_raw = payload.get("semantic_match_sync_on_upsert")
    semantic_sync = bool(semantic_sync_raw) if "semantic_match_sync_on_upsert" in payload else None
    embedding_provider_raw = payload.get("embedding_provider")
    embedding_provider = str(embedding_provider_raw) if "embedding_provider" in payload else None
    threshold_raw = payload.get("semantic_match_threshold")
    threshold: float | None = None
    if "semantic_match_threshold" in payload and threshold_raw not in (None, ""):
        try:
            threshold = float(threshold_raw)
        except (TypeError, ValueError):
            return JSONResponse(
                status_code=422,
                content={"detail": "semantic_match_threshold must be a float"},
            )
    try:
        s = await settings_service.update_llm(
            session,
            user_id=1,
            provider=LLMProviderEnum(provider) if provider else None,
            model=payload.get("llm_model"),
            fallback_provider=(LLMProviderEnum(fallback_provider) if fallback_provider else None),
            semantic_match_enabled=semantic_enabled,
            embedding_provider=embedding_provider,
            semantic_match_threshold=threshold,
            semantic_match_sync_on_upsert=semantic_sync,
        )
    except ValueError as exc:
        return JSONResponse(status_code=422, content={"detail": str(exc)})
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
    request: Request,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    """Plan 78 (0.4.0.13 + 0.4.0.20) — form-encoded support added for the
    new per-board cap editor + dry-run toggle alongside the existing JSON
    body path. Form payloads collapse `<board>_cap` fields into
    `auto_apply_per_board_daily_caps`; absent fields are treated as "skip"
    so partial PUTs from individual toggles don't clobber unrelated state.
    """
    from models import ApplicationBoard

    is_form = _is_form_request(request)
    if is_form:
        form = await request.form()
        payload: dict[str, Any] = {k: str(v) for k, v in form.items()}
    else:
        try:
            raw = await request.json()
        except Exception:  # noqa: BLE001
            raw = {}
        payload = raw if isinstance(raw, dict) else {}

    # Plan 59 / 0.2.7.12 § D.3 — HTMX checkbox tri-state idiom: an absent
    # key means "skip" (partial PUTs), a present key (truthy or falsy)
    # means "set bool(value)". Required so unchecking the toggle in the
    # Settings UI persists False rather than silently skipping assignment.
    immediate = (
        bool(payload.get("auto_apply_immediate_dispatch"))
        if "auto_apply_immediate_dispatch" in payload
        else None
    )
    # Plan 78 § D.5 — dry-run toggle with the same tri-state idiom.
    dry_run = bool(payload.get("auto_apply_dry_run")) if "auto_apply_dry_run" in payload else None

    # Plan 78 § D.3 — assemble per-board caps from either flat form fields
    # (`<board>_cap`) or a pre-shaped `auto_apply_per_board_daily_caps` dict
    # (JSON callers). Empty string in form = "no cap" → omit board entry.
    per_board: dict[str, int] | None = None
    if is_form:
        # Form path only assembles the per-board sub-payload when at least
        # one `<board>_cap` field is present. Otherwise None = skip (preserve
        # existing value).
        collected: dict[str, int] = {}
        any_seen = False
        for board in ApplicationBoard:
            field_name = f"{board.value}_cap"
            if field_name in payload:
                any_seen = True
                raw_val = payload[field_name].strip() if payload[field_name] else ""
                if not raw_val:
                    continue
                try:
                    iv = int(raw_val)
                except ValueError:
                    continue
                if iv > 0:
                    collected[board.value] = iv
        if any_seen:
            per_board = collected
    elif "auto_apply_per_board_daily_caps" in payload:
        v = payload["auto_apply_per_board_daily_caps"]
        per_board = v if isinstance(v, dict) else {}

    s = await settings_service.update_auto_apply(
        session,
        user_id=1,
        auto_apply_enabled=payload.get("auto_apply_enabled"),
        auto_apply_score_threshold=payload.get("auto_apply_score_threshold"),
        auto_apply_daily_cap=payload.get("auto_apply_daily_cap"),
        eager_review_generation=payload.get("eager_review_generation"),
        daily_llm_cost_cap_usd=payload.get("daily_llm_cost_cap_usd"),
        auto_apply_immediate_dispatch=immediate,
        auto_apply_per_board_daily_caps=per_board,
        auto_apply_dry_run=dry_run,
    )
    await session.commit()
    return {
        "auto_apply_enabled": s.auto_apply_enabled,
        "auto_apply_score_threshold": s.auto_apply_score_threshold,
        "auto_apply_daily_cap": s.auto_apply_daily_cap,
        "eager_review_generation": s.eager_review_generation,
        "daily_llm_cost_cap_usd": s.daily_llm_cost_cap_usd,
        "auto_apply_immediate_dispatch": s.auto_apply_immediate_dispatch,
        "auto_apply_per_board_daily_caps": s.auto_apply_per_board_daily_caps,
        "auto_apply_dry_run": s.auto_apply_dry_run,
    }


@router.post(
    "/api/v1/settings/auto-apply/drain-queue",
    name="api_settings_auto_apply_drain",
)
async def post_auto_apply_drain(
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    """Plan 78 § D.4 — global drain: flip every QUEUED_FOR_AUTO_APPLY Job
    back to SAVED. Returns `{drained: N}`. CSRF + auth gated.
    """
    from services import application_service as application_service_mod
    from ui.routes.settings import _effective_user_id

    # Resolve per authed caller (hacker MED-2 PR #193 fix). Pattern matches
    # put_sources (line 403) + put_generation (line 487). Avoids destructive
    # cross-tenant drain in any future allow_multiple_users path.
    user_id = _effective_user_id(_user)
    drained = await application_service_mod.drain_auto_apply_queue(
        session, user_id=user_id, reason="settings_drain"
    )
    await session.commit()
    return {"drained": drained}


def _split_keywords(raw: str) -> list[str]:
    """Comma-split, strip whitespace, drop empties. Used by form-encoded
    `<source>_keywords` form fields (plan 58 / 0.2.7.06)."""
    return [token.strip() for token in raw.split(",") if token.strip()]


def _form_to_sources_payload(form: dict[str, str]) -> dict[str, Any]:
    """Reassemble flat HTMX form fields into the kwarg shape expected by
    `settings_service.update_sources` (plan 58 / 0.2.7.06).

    Rate-limit shape — flat `<source>_rpm` / `<source>_lo` / `<source>_hi`
    fields collapse into a nested `scraper_rate_limits[<source>]` dict per
    `RateLimitConfig`. Keywords/location shape — `<source>_keywords` is
    comma-split into list[str]; `<source>_location` passes through.
    """
    payload: dict[str, Any] = {}
    rate_limits: dict[str, dict[str, float]] = {}
    for source in JobSource:
        sv = source.value
        rpm = form.get(f"{sv}_rpm")
        lo = form.get(f"{sv}_lo")
        hi = form.get(f"{sv}_hi")
        if rpm is not None and lo is not None and hi is not None:
            try:
                rate_limits[sv] = {
                    "rpm": float(rpm),
                    "delay_lo": float(lo),
                    "delay_hi": float(hi),
                }
            except (TypeError, ValueError):
                # Surface as 422 downstream via RateLimitConfig validator
                # — preserve the raw shape so the validator sees the bad input.
                rate_limits[sv] = {"rpm": rpm, "delay_lo": lo, "delay_hi": hi}  # type: ignore[dict-item]
    if rate_limits:
        payload["scraper_rate_limits"] = rate_limits

    if (raw := form.get("linkedin_keywords")) is not None:
        payload["linkedin_keywords"] = _split_keywords(raw)
    if (loc := form.get("linkedin_location")) is not None:
        payload["linkedin_location"] = loc
    if (raw := form.get("indeed_keywords")) is not None:
        payload["indeed_keywords"] = _split_keywords(raw)
    if (loc := form.get("indeed_location")) is not None:
        payload["indeed_location"] = loc
    return payload


@router.put("/api/v1/settings/sources", name="api_settings_sources_put")
async def put_sources(
    request: Request,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    """Update Settings · Sources fields.

    Two content types accepted (plan 58 / 0.2.7.06):
      * `application/x-www-form-urlencoded` (HTMX paired editors) → returns
        the re-rendered `pages/_settings_sources.html` partial as HTML.
      * `application/json` (machine consumers + the per-source enable toggle
        already wired to this endpoint) → returns JSON with the post-update
        Settings shape.

    IDOR scoping via `_effective_user_id` (plan 56 / 0.2.7.02 pattern); CSRF
    via the shared `require_csrf` dep (plan 44 / 0.2.0.11b pattern).
    Body parsing is inline (mirroring `put_llm`) so a form-encoded request
    doesn't trip FastAPI's JSON validator before the form branch fires.
    """
    is_form = _is_form_request(request)
    if is_form:
        form = await request.form()
        form_dict = {k: str(v) for k, v in form.items()}
        body = _form_to_sources_payload(form_dict)
    else:
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            body = {}
        if not isinstance(body, dict):
            body = {}

    # Lazy-import to avoid cyclic dep with the UI route module.
    from ui.routes.settings import _effective_user_id

    user_id = _effective_user_id(_user)

    try:
        s = await settings_service.update_sources(
            session,
            user_id=user_id,
            sources_enabled=body.get("sources_enabled"),
            source_schedules=body.get("source_schedules"),
            workday_companies=body.get("workday_companies"),
            linkedin_keywords=body.get("linkedin_keywords"),
            linkedin_location=body.get("linkedin_location"),
            indeed_keywords=body.get("indeed_keywords"),
            indeed_location=body.get("indeed_location"),
            scraper_rate_limits=body.get("scraper_rate_limits"),
        )
    except ValidationError as exc:
        return JSONResponse(
            status_code=422,
            content={
                "detail": "invalid scraper_rate_limits",
                "errors": exc.errors(include_url=False, include_context=False, include_input=False),
            },
        )
    await session.commit()

    if is_form:
        from ui.routes.settings import _ctx_for_tab
        from ui.templates_setup import templates as ui_templates

        ctx = await _ctx_for_tab(request, "sources", session=session, user_id=user_id)
        ctx["save_status"] = "saved"
        return ui_templates.TemplateResponse(
            request,
            "pages/_settings_sources.html",
            ctx,
        )

    return {
        "sources_enabled": s.sources_enabled,
        "source_schedules": s.source_schedules,
        "workday_companies": s.workday_companies,
        "linkedin_keywords": s.linkedin_keywords,
        "linkedin_location": s.linkedin_location,
        "indeed_keywords": s.indeed_keywords,
        "indeed_location": s.indeed_location,
        "scraper_rate_limits": s.scraper_rate_limits,
    }


@router.put("/api/v1/settings/generation", name="api_settings_generation_put")
async def put_generation(
    request: Request,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    """Update Settings · Generation tab fields — plan 67 (0.3.4) § C.6.

    Two content types:
      * `application/x-www-form-urlencoded` (HTMX form) -> re-renders the
        Generation tab partial.
      * `application/json` -> returns JSON post-update payload.

    Fields:
      - generation_tier ("free" | "premium")
      - originality_api_key (string; empty = clear)
      - tier_2_evasion_enabled (bool; absent key = skip)

    IDOR scoped via `_effective_user_id`; CSRF enforced by `require_csrf`.
    """
    from ui.routes.settings import _effective_user_id

    is_form = _is_form_request(request)
    if is_form:
        form = await request.form()
        payload = {k: str(v) for k, v in form.items()}
    else:
        try:
            payload = await request.json()
        except Exception:  # noqa: BLE001
            payload = {}
        if not isinstance(payload, dict):
            payload = {}

    user_id = _effective_user_id(_user)
    generation_tier = payload.get("generation_tier")
    # Form template always submits `originality_api_key` (password input has no
    # `value=`, so the browser sends empty string on every save). Treat empty
    # as "leave existing key untouched"; only a non-empty new value overwrites.
    # JSON callers can still send explicit empty string to clear via the
    # dedicated `originality_api_key_clear` sentinel.
    originality_api_key_raw = payload.get("originality_api_key")
    originality_api_key: str | None = None
    if (
        originality_api_key_raw is not None
        and isinstance(originality_api_key_raw, str)
        and originality_api_key_raw.strip()
    ):
        originality_api_key = originality_api_key_raw.strip()
    clear_key = bool(payload.get("originality_api_key_clear"))
    tier_2_evasion_raw = payload.get("tier_2_evasion_enabled")
    tier_2_evasion = bool(tier_2_evasion_raw) if "tier_2_evasion_enabled" in payload else None

    try:
        s = await settings_service.update_generation(
            session,
            user_id=user_id,
            generation_tier=generation_tier if generation_tier else None,
            originality_api_key=originality_api_key,
            originality_api_key_clear=clear_key,
            tier_2_evasion_enabled=tier_2_evasion,
        )
    except ValueError as exc:
        return JSONResponse(status_code=422, content={"detail": str(exc)})
    await session.commit()

    if is_form:
        from ui.routes.settings import _ctx_for_tab
        from ui.templates_setup import templates as ui_templates

        ctx = await _ctx_for_tab(request, "generation", session=session, user_id=user_id)
        ctx["save_status"] = "saved"
        return ui_templates.TemplateResponse(
            request,
            "pages/_settings_generation.html",
            ctx,
        )

    return {
        "generation_tier": s.generation_tier,
        "originality_api_key_configured": bool(s.originality_api_key),
        "tier_2_evasion_enabled": s.tier_2_evasion_enabled,
    }


@router.put("/api/v1/settings/notifications", name="api_settings_notifications_put")
async def put_notifications(
    payload: Annotated[dict[str, Any] | None, Body()] = None,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
):
    """Update notification preferences.

    Plan 26 (0.2.0.01): rejects any payload carrying `discord_webhook_url`,
    `telegram_bot_token`, or `telegram_chat_id` with a 422 + env-migration
    guidance. Webhook URL, bot token, and chat ID are env-only post-vault.
    """
    payload = payload or {}
    if (
        payload.get("discord_webhook_url")
        or payload.get("telegram_bot_token")
        or payload.get("telegram_chat_id")
    ):
        return JSONResponse(
            status_code=422,
            content={
                "detail": (
                    "Discord webhook URL, Telegram bot token, and Telegram "
                    "chat ID are configured via env vars (DISCORD_WEBHOOK_URL "
                    "/ TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID) starting in "
                    "0.2.0. Edit .env and restart. See README § Configuration."
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


# ── JWT signing-key rotation (plan 62 / 0.2.7.07) ────────────────────────

# Single-tenant Naavik deployments pin tenant_id=1. Cloud multi-tenancy
# (`0.8.0.NN`) will introduce a per-request tenant resolver that derives the
# tenant from the authenticated user (or org membership).
_SELF_HOST_TENANT_ID = 1


@router.post(
    "/api/v1/settings/security/rotate-jwt-key",
    name="api_settings_security_rotate_jwt_key",
)
async def post_rotate_jwt_key(
    request: Request,
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_authed_session),
    _csrf: None = Depends(require_csrf),
):
    """Operator-triggered JWT signing-key rotation.

    Issues a fresh RS256 keypair, demotes the current ACTIVE key to
    RETIRING (in-flight tokens still verify within `Settings.jwt_rotation_grace_days`),
    and persists. Returns the re-rendered Settings · Security card HTML for
    HTMX swap. CSRF + IDOR enforced via deps.

    Single-tenant: rotation targets `_SELF_HOST_TENANT_ID` (= 1). Cloud
    multi-tenancy follow-up `0.8.0.NN` swaps this for per-request tenant
    resolution.
    """
    from sqlalchemy.exc import IntegrityError

    from services.jwt_rotation_service import rotate_tenant_key
    from ui.routes.settings import _build_security_view, _effective_user_id
    from ui.templates_setup import templates

    user_id = _effective_user_id(_user)
    actor = f"ui:{_user.email}" if _user is not None else "ui:dev"

    try:
        await rotate_tenant_key(session, tenant_id=_SELF_HOST_TENANT_ID, actor=actor)
        await session.commit()
    except IntegrityError:
        # Partial unique index `ix_tenant_signing_key_one_active_per_tenant`
        # fired — concurrent rotation win/lose race. Rollback + tell caller
        # to retry; the other rotation already produced a fresh ACTIVE.
        await session.rollback()
        return JSONResponse(
            status_code=409,
            content={"detail": "another rotation is in progress; refresh to see the new key"},
        )

    ctx = {"security": await _build_security_view(session, user_id=user_id)}
    return templates.TemplateResponse(request, "pages/_settings_security.html", ctx)
