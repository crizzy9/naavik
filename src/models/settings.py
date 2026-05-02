"""Settings singleton (one row per user).

Per DATA_MODEL.md § C `Settings` + § L consumer mapping. Includes:
- `eager_review_generation` (cost-aware DRAFT generation flag)
- `daily_llm_cost_cap_usd` (cap-trigger flips eager → lazy mid-day)
- `portfolio_cors_allowed_origins` (configurable list per Q10)
- `debug` (gates `/_design/components` after Wave 4 swap)

No secret material — every API key, OAuth refresh token, IMAP password,
ATS cookie, Discord webhook URL, Telegram bot token, Netlify hook lives in
`~/.naavik/secrets.enc` via `services/vault.py`. Settings stores at most a
fingerprint (`llm_api_key_fingerprint: sha256:...`) so the UI can show
"key set" without holding the key.
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
    llm_api_key_fingerprint: str | None = None
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

    # Channels (URL/token in vault; bool here flags whether configured)
    discord_webhook_configured: bool = Field(default=False)
    telegram_bot_configured: bool = Field(default=False)
    portfolio_webhook_configured: bool = Field(default=False)
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
    scraper_proxy_configured: bool = Field(default=False)

    # Deployment
    deployment_mode: DeploymentMode = Field(default=DeploymentMode.SELF_HOSTED)

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

