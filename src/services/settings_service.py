"""Settings service — Wave 4 of plan 10 § B.8.

DB-backed CRUD for the per-user `Settings` singleton. Secrets (API keys,
OAuth tokens, webhook URLs) flow through the vault — never stored on the
Settings row directly.

Wave 4 ships: get/upsert + per-tab updates. Scheduler reschedule on sources
save is a stub here (the APScheduler integration ships in Wave 6).
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import LLMProvider as LLMProviderEnum
from models import Settings
from services import vault as vault_svc

# Vault scope keys
_LLM_SCOPE = "llm"
_NOTIFICATIONS_SCOPE = "notifications"
_INTEGRATIONS_SCOPE = "integrations"


async def get_or_create(session: AsyncSession, user_id: int) -> Settings:
    stmt = select(Settings).where(Settings.user_id == user_id)
    row = (await session.exec(stmt)).one_or_none()
    if row is not None:
        return row
    row = Settings(user_id=user_id)
    session.add(row)
    await session.flush()
    return row


def _fingerprint_for_key(api_key: str) -> str:
    return "sha256:" + hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:32]


# ── Per-tab updates ──────────────────────────────────────────────────────


async def update_llm(
    session: AsyncSession,
    user_id: int,
    *,
    provider: LLMProviderEnum | None = None,
    model: str | None = None,
    api_key: str | None = None,
    fallback_provider: LLMProviderEnum | None = None,
) -> Settings:
    s = await get_or_create(session, user_id)
    if provider is not None:
        s.llm_provider = provider
    if model is not None:
        s.llm_model = model
    if fallback_provider is not None:
        s.llm_fallback_provider = fallback_provider
    if api_key is not None:
        # Route the actual key through the vault — DB stores fingerprint only.
        target_provider = (provider or s.llm_provider).value
        vault_svc.set(_LLM_SCOPE, target_provider, api_key, caller="settings_service")
        s.llm_api_key_fingerprint = _fingerprint_for_key(api_key)
    s.updated_at = datetime.now(UTC)
    session.add(s)
    await session.flush()
    return s


async def update_auto_apply(
    session: AsyncSession,
    user_id: int,
    *,
    auto_apply_enabled: bool | None = None,
    auto_apply_score_threshold: float | None = None,
    auto_apply_daily_cap: int | None = None,
    eager_review_generation: bool | None = None,
    daily_llm_cost_cap_usd: float | None = None,
) -> Settings:
    s = await get_or_create(session, user_id)
    if auto_apply_enabled is not None:
        s.auto_apply_enabled = auto_apply_enabled
    if auto_apply_score_threshold is not None:
        s.auto_apply_score_threshold = float(auto_apply_score_threshold)
    if auto_apply_daily_cap is not None:
        s.auto_apply_daily_cap = auto_apply_daily_cap
    if eager_review_generation is not None:
        s.eager_review_generation = eager_review_generation
    if daily_llm_cost_cap_usd is not None:
        s.daily_llm_cost_cap_usd = float(daily_llm_cost_cap_usd)
    s.updated_at = datetime.now(UTC)
    session.add(s)
    await session.flush()
    return s


async def update_sources(
    session: AsyncSession,
    user_id: int,
    *,
    sources_enabled: dict[str, bool] | None = None,
    source_schedules: dict[str, str] | None = None,
    workday_companies: list[str] | None = None,
) -> Settings:
    s = await get_or_create(session, user_id)
    if sources_enabled is not None:
        s.sources_enabled = sources_enabled
    if source_schedules is not None:
        s.source_schedules = source_schedules
    if workday_companies is not None:
        s.workday_companies = workday_companies
    s.updated_at = datetime.now(UTC)
    session.add(s)
    await session.flush()
    # APScheduler reschedule fires here in Wave 6 — Phase 1 stubs the scheduler.
    return s


async def update_notifications(
    session: AsyncSession,
    user_id: int,
    *,
    notify_threshold: float | None = None,
    notify_on_errors: bool | None = None,
    notifications_enabled: dict[str, bool] | None = None,
    discord_webhook_url: str | None = None,
    telegram_bot_token: str | None = None,
) -> Settings:
    s = await get_or_create(session, user_id)
    if notify_threshold is not None:
        s.notify_threshold = float(notify_threshold)
    if notify_on_errors is not None:
        s.notify_on_errors = notify_on_errors
    if notifications_enabled is not None:
        s.notifications_enabled = notifications_enabled
    if discord_webhook_url is not None:
        if discord_webhook_url:
            vault_svc.set(
                _NOTIFICATIONS_SCOPE,
                "discord_webhook_url",
                discord_webhook_url,
                caller="settings_service",
            )
            s.discord_webhook_configured = True
        else:
            vault_svc.delete(_NOTIFICATIONS_SCOPE, "discord_webhook_url", caller="settings_service")
            s.discord_webhook_configured = False
    if telegram_bot_token is not None:
        if telegram_bot_token:
            vault_svc.set(
                _NOTIFICATIONS_SCOPE,
                "telegram_bot_token",
                telegram_bot_token,
                caller="settings_service",
            )
            s.telegram_bot_configured = True
        else:
            vault_svc.delete(_NOTIFICATIONS_SCOPE, "telegram_bot_token", caller="settings_service")
            s.telegram_bot_configured = False
    s.updated_at = datetime.now(UTC)
    session.add(s)
    await session.flush()
    return s


async def update_account_password(
    session: AsyncSession,
    user_id: int,
    *,
    current_password: str,
    new_password: str,
) -> bool:
    """Verify current password, then store new bcrypt hash on `User.password_hash`."""
    from models import User
    from services.auth import hash_password, verify_password

    stmt = select(User).where(User.id == user_id, User.deleted_at.is_(None))
    user = (await session.exec(stmt)).one_or_none()
    if user is None:
        return False
    if not verify_password(current_password, user.password_hash):
        return False
    user.password_hash = hash_password(new_password)
    user.updated_at = datetime.now(UTC)
    session.add(user)
    await session.flush()
    return True


# ── Deployment metadata ──────────────────────────────────────────────────


async def get_deployment_info(session: AsyncSession, user_id: int) -> dict[str, Any]:
    """Return the bundle Settings · Deployment renders."""
    s = await get_or_create(session, user_id)

    return {
        "deployment_mode": s.deployment_mode.value,
        "vault": {
            "fingerprint": vault_svc.fingerprint(),
            "expected_fingerprint": vault_svc.expected_fingerprint(),
            "is_locked": vault_svc.is_locked(),
        },
        "debug": s.debug,
        "settings_user_id": s.user_id,
    }
