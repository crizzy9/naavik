"""Settings singleton (one row per user).

Per DATA_MODEL.md § C `Settings` + § L consumer mapping. Includes:
- `eager_review_generation` (cost-aware DRAFT generation flag)
- `daily_llm_cost_cap_usd` (cap-trigger flips eager → lazy mid-day)
- `portfolio_cors_allowed_origins` (configurable list per Q10)
- `debug` (gates `/_design/components` after Wave 4 swap)

No secret material — every API key, OAuth refresh token, IMAP password,
ATS cookie, Discord webhook URL, Telegram bot token, Netlify hook lives in
the `.env` file consumed by `pydantic-settings` (per plan 26 / `0.2.0.01`,
the AES-256-GCM vault was deleted in favor of standard env-loading).
`services/env_secrets.py` exposes presence indicators for the Settings UI
without surfacing values.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlmodel import Field, SQLModel

from ._common import utcnow
from .enums import DeploymentMode, LLMProvider


class Settings(SQLModel, table=True):
    __tablename__ = "settings"

    user_id: int = Field(primary_key=True, foreign_key="user.id")

    # LLM
    llm_provider: LLMProvider = Field(default=LLMProvider.ANTHROPIC)
    llm_model: str = Field(default="claude-3.5-sonnet-20250219")
    llm_fallback_provider: LLMProvider | None = None

    # Auto-apply
    auto_apply_enabled: bool = Field(default=False)
    auto_apply_score_threshold: float = Field(default=0.85)
    auto_apply_daily_cap: int | None = None

    # Cost-aware DRAFT generation
    eager_review_generation: bool = Field(default=True)
    daily_llm_cost_cap_usd: float | None = None

    # Notifications
    notify_threshold: float = Field(default=0.80)
    notify_on_errors: bool = Field(default=True)
    notifications_enabled: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
    )

    # Channels — URL/token configured via env vars (DISCORD_WEBHOOK_URL,
    # TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, PORTFOLIO_WEBHOOK_URL).
    # `services/env_secrets.py` exposes presence indicators.
    portfolio_cors_allowed_origins: list[str] = Field(
        default_factory=lambda: ["https://crypticsoul.dev"],
        sa_column=Column(
            ARRAY(String),
            nullable=False,
            server_default="{https://crypticsoul.dev}",
        ),
    )

    # Sources
    sources_enabled: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
    )
    source_schedules: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
    )
    workday_companies: list[str] = Field(
        default_factory=list,
        sa_column=Column(ARRAY(String), nullable=False, server_default="{}"),
    )

    # Plan 35 (0.2.0.10): per-user search inputs for LinkedIn + Indeed crons.
    # `linkedin_keywords` / `indeed_keywords` are list[str]; cron composes
    # them into ScrapeQuery.keywords. `linkedin_location` / `indeed_location`
    # are free-text strings (LinkedIn accepts "United States", "Remote", etc).
    linkedin_keywords: list[str] | None = Field(
        default=None,
        sa_column=Column(ARRAY(String), nullable=True),
    )
    linkedin_location: str | None = None
    indeed_keywords: list[str] | None = Field(
        default=None,
        sa_column=Column(ARRAY(String), nullable=True),
    )
    indeed_location: str | None = None

    # Plan 35 (0.2.0.10): per-source consecutive-FAILED counter. Cron resets
    # to 0 on first SUCCESS / PARTIAL; auto-skip after 3 with one Discord
    # admin alert. Key = JobSource.value (e.g. "linkedin"); value = int.
    consecutive_scrape_failures: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
    )

    # Deployment
    deployment_mode: DeploymentMode = Field(default=DeploymentMode.SELF_HOSTED)

    # Plan 10b (item 4, 2026-05-03): single-user signup gate.
    # When False (default), POST /api/v1/auth/signup returns 403 once any
    # User row exists — keeps a self-hosted instance from accidentally
    # turning into a multi-tenant SaaS. Multi-user proper lands in Phase 2+.
    allow_multiple_users: bool = Field(default=False)

    # Misc
    debug: bool = Field(default=False)

    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
