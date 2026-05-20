"""Settings service — Wave 4 of plan 10 § B.8.

DB-backed CRUD for the per-user `Settings` singleton. Plan 26 (0.2.0.01)
deleted the encrypted vault: every secret (LLM API keys, OAuth refresh
tokens, IMAP passwords, ATS cookies, Discord webhook URL, Telegram bot
token, Netlify build hook) now flows through env vars consumed by
`pydantic-settings` in `src/config.py`. Settings stores no secret material
and exposes no presence indicators — those are runtime-derived via
`services/env_secrets.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import LLMProvider as LLMProviderEnum
from models import Settings


async def get_or_create(session: AsyncSession, user_id: int) -> Settings:
    stmt = select(Settings).where(Settings.user_id == user_id)
    row = (await session.exec(stmt)).one_or_none()
    if row is not None:
        return row
    row = Settings(user_id=user_id)
    session.add(row)
    await session.flush()
    return row


# ── Per-tab updates ──────────────────────────────────────────────────────


async def update_llm(
    session: AsyncSession,
    user_id: int,
    *,
    provider: LLMProviderEnum | None = None,
    model: str | None = None,
    fallback_provider: LLMProviderEnum | None = None,
) -> Settings:
    s = await get_or_create(session, user_id)
    if provider is not None:
        s.llm_provider = provider
    if model is not None:
        s.llm_model = model
    if fallback_provider is not None:
        s.llm_fallback_provider = fallback_provider
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
    linkedin_keywords: list[str] | None = None,
    linkedin_location: str | None = None,
    indeed_keywords: list[str] | None = None,
    indeed_location: str | None = None,
) -> Settings:
    s = await get_or_create(session, user_id)
    if sources_enabled is not None:
        s.sources_enabled = sources_enabled
    if source_schedules is not None:
        s.source_schedules = source_schedules
    if workday_companies is not None:
        s.workday_companies = workday_companies
    if linkedin_keywords is not None:
        s.linkedin_keywords = linkedin_keywords
    if linkedin_location is not None:
        s.linkedin_location = linkedin_location
    if indeed_keywords is not None:
        s.indeed_keywords = indeed_keywords
    if indeed_location is not None:
        s.indeed_location = indeed_location
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
) -> Settings:
    s = await get_or_create(session, user_id)
    if notify_threshold is not None:
        s.notify_threshold = float(notify_threshold)
    if notify_on_errors is not None:
        s.notify_on_errors = notify_on_errors
    if notifications_enabled is not None:
        s.notifications_enabled = notifications_enabled
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
    """Return the bundle Settings · Deployment renders.

    Plan 26 (0.2.0.01): the vault status triplet (`vault_locked`,
    `vault_fingerprint_stored`, `vault_fingerprint_expected`) is removed
    along with the vault. Self-hosters set secrets via `.env`; filesystem
    permissions are the operative defense.
    """
    s = await get_or_create(session, user_id)
    return {
        "deployment_mode": s.deployment_mode.value,
        "debug": s.debug,
        "settings_user_id": s.user_id,
    }
