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
    # Plan 59 (0.2.7.12): when True, right-swipe in Discover schedules a
    # transient `scheduler.jobs:auto_apply` one-off via APScheduler
    # `DateTrigger(now)` instead of waiting for the 5-min cron tick.
    # Default False preserves the cron-only behavior.
    auto_apply_immediate_dispatch: bool = Field(default=False)
    # Plan 63 (0.2.7.10) § D.5 — dual-gate with `auto_apply_score_threshold`.
    # Adapter emits `SubmissionResult.confidence` (HTTP adapters always 1.0;
    # Generic emits LLM-form-fill confidence); below this threshold → revert
    # to DRAFT + surface in manual-review queue. Per-adapter PRs source the
    # `confidence` field; this knob is the operator-tunable threshold.
    auto_apply_adapter_confidence_threshold: float = Field(default=0.7)
    # Plan 78 § D.3 (0.4.0.13) — per-board operator-tunable daily caps.
    # JSONB shape `{ApplicationBoard.value: int}`; missing key → no per-board
    # limit; empty dict → fall through to the global `auto_apply_daily_cap`.
    # Operator tunes via Settings · Auto-apply UI.
    auto_apply_per_board_daily_caps: dict[str, int] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
    )
    # Plan 78 § D.5 (0.4.0.20) — auto-apply dry-run mode. When True,
    # `process_auto_apply_queue` short-circuits BEFORE `submit_draft` so no
    # ATS network call ever fires; `submission_artifacts.dry_run_at` records
    # what would have submitted on a real cron tick.
    auto_apply_dry_run: bool = Field(default=False)

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
    # to 0 on first SUCCESS / PARTIAL; one Discord admin alert fires when
    # the counter crosses threshold=3 (2 → 3). Cron never skips on counter —
    # always runs so the counter can recover. Key = JobSource.value (e.g.
    # "linkedin"); value = int failure count.
    consecutive_scrape_failures: dict[str, int] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
    )

    # Plan 38 (0.2.0.13): per-source operator-tunable rate-limit overrides.
    # Nested shape `{"linkedin": {"rpm": 0.4, "delay_lo": 3.0, "delay_hi": 7.0}}`
    # validated via `scraper/rate_limit.py:RateLimitConfig`. Empty dict
    # falls through to the class-attr fallback table; missing per-source key
    # also falls through. Operators tune via Settings · Sources UI (Phase 6+).
    scraper_rate_limits: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
    )

    # Plan 61 (0.2.7.14 + 0.2.7.16): semantic-match toggle + per-user embedding
    # provider + cosine-sim floor. Default OFF; provider routing reads
    # `OPENAI_API_KEY` / `OLLAMA_BASE_URL` env presence via env_secrets.
    # `semantic_match_sync_on_upsert` — opt-in sync trigger inside
    # `job_service.upsert_job`; default OFF (nightly-only) so scraper p50
    # isn't bombed by embedding-call latency. See `decision D3`.
    semantic_match_enabled: bool = Field(default=False)
    embedding_provider: str | None = Field(default=None, max_length=32)
    semantic_match_threshold: float = Field(default=0.65)
    semantic_match_sync_on_upsert: bool = Field(default=False)

    # Plan 66 (0.3.1): tailored-bundle generation knobs. `ai_writing_voice_samples`
    # supplements the auto-extracted voice corpus (Bullet.text + Profile.summary_*
    # + ProfileAnswer.answer). `cover_letter_format` overrides adaptive dispatch.
    # `tier_2_evasion_enabled` opts into experimental humanization (default off).
    # `resume_template_preference` overrides board-driven template selection.
    # `parse_fidelity_threshold` tunes the OQ-7 smart-default tiers.
    ai_writing_voice_samples: str = Field(default="", max_length=5000)
    cover_letter_format: str = Field(default="auto", max_length=20)
    tier_2_evasion_enabled: bool = Field(default=False)
    resume_template_preference: str = Field(default="auto", max_length=20)
    parse_fidelity_threshold: float = Field(default=0.75)

    # Plan 67 (0.3.4): PREMIUM-tier Claude-mythos generation. `generation_tier`
    # routes `bundle_generator.generate_bundle` through the PREMIUM path
    # (council + detector loop + critique + tool-loop). `originality_api_key`
    # is per-user opt-in for the real-detector spot-check at convergence
    # (Settings DB column per AGENTS.md § Key Conventions § CLI — vault-sunset
    # compliant; env-var would force a redeploy on rotation).
    generation_tier: str = Field(default="free", max_length=20)
    originality_api_key: str | None = Field(default=None, max_length=200)

    # Plan 65 (0.3.0.02): per-tag operator-tunable scoring weights.
    # JSONB shape `{tag_value: float}`; empty dict → all tags weighted 1.0.
    # Validator (services/scorer/weights.py:PerDimWeights) drops unknown
    # keys + clamps values to [0.0, 3.0]. Operator tunes via Settings · LLM
    # editor (UI ships in 0.3.2.04). Defaults to neutral so every user
    # ships the same baseline; per-profile bias is opt-in.
    score_per_dim_weights: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
    )

    # Plan 62 (0.2.7.07): JWT signing-key rotation cadence + dual-key grace.
    # `jwt_rotation_days` — cron promotes ACTIVE → RETIRING when an ACTIVE
    # key's `created_at` is older than this. Default 90, configurable 30-365.
    # `jwt_rotation_grace_days` — RETIRING rows are still accepted for
    # verification for this many days, then flipped RETIRED. Default 7,
    # configurable 1-30. Operator tunes via Settings · Security.
    jwt_rotation_days: int = Field(default=90)
    jwt_rotation_grace_days: int = Field(default=7)

    # Deployment
    deployment_mode: DeploymentMode = Field(default=DeploymentMode.SELF_HOSTED)

    # Plan 0.7.0.48 (2026-05-24): deprecated — field retained for schema
    # compatibility but no longer read by code. Multi-user signup is the
    # default; first user becomes admin. Drop via alembic migration in
    # 0.7.0.49 follow-up.
    allow_multiple_users: bool = Field(default=True)

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
