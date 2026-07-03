from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql+asyncpg://naavik:password@localhost:5432/naavik"

    # Security
    secret_key: str = "change-me-in-production"

    # LLM Providers (all optional - user configures in settings)
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"

    # Optional Integrations
    discord_webhook_url: str | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    portfolio_webhook_url: str | None = None

    # Data dir (mirrors production /app/.naavik in Docker, ~/.naavik on NixOS)
    data_dir: str = ".naavik"

    # Server
    host: str = "0.0.0.0"
    port: int = 8003

    # Scraper config — plan 33 / 0.2.0.07. All optional; cron skips a source
    # silently when its company-list is unset. CSV parsed by pydantic-settings
    # (e.g. `GREENHOUSE_COMPANIES=anthropic,openai,scale`).
    scraper_rsshub_url: str | None = None
    workday_companies: list[str] | None = None
    greenhouse_companies: list[str] | None = None
    lever_companies: list[str] | None = None
    ashby_companies: list[str] | None = None

    # ATS adapter credentials — plan 63 / 0.2.7.10 § D.3. Env-based per
    # post-vault pattern. Each slot is OPTIONAL; the adapter's `submit()`
    # returns `FAILURE_AUTH_REQUIRED` predictably when the slot is unset.
    # `services/env_secrets.py` exposes presence indicators for Settings UI.
    # Adapter implementations land in 0.4.0.NN (Workday) + 0.8.0.NN
    # (LinkedIn / Indeed / Generic); these slots are reserved + read at
    # adapter-instantiation time (NOT once at startup).
    workday_login_token: str | None = None
    # Also the bootstrap `li_at` for `services/linkedin_resolver.py` — it seeds
    # the persistent Chromium profile under DATA_DIR/linkedin/profile so the
    # authenticated apply-target resolver (Tier B) can read the real offsite
    # URL. Refresh via `scripts/linkedin_login.py`.
    linkedin_session_cookie: str | None = None
    indeed_session_cookie: str | None = None
    ats_generic_llm_confidence_threshold: float = 0.7

    # LinkedIn proxy — plan 64 / 0.2.7.11. Env-only per § D.3 (multi-tenant
    # DB-stored deferred to 0.8.0.NN). Accepts `http://user:pass@host:port`,
    # `https://...`, `socks5://...`. URL validated FAIL LOUD at boot per § D.6
    # (proxy outage MUST stop the cron, never silently degrade to direct).
    # `linkedin_proxy_provider_hint` is an opaque telemetry label persisted in
    # `JobScrapeRun.raw_meta.proxy.provider_hint` for cost analysis only.
    linkedin_proxy_url: str | None = None
    linkedin_proxy_provider_hint: str | None = None

    @field_validator("linkedin_proxy_url", mode="after")
    @classmethod
    def _validate_linkedin_proxy_url(cls, v: str | None) -> str | None:
        """Plan 64 § D.6 FAIL LOUD — invalid URL refuses boot.

        Lazy import of `ProxyURLConfig` to avoid a circular: `scraper.proxy`
        imports `config.settings` at call-time.
        """
        if v is None or v == "":
            return None
        from scraper.proxy import ProxyURLConfig

        ProxyURLConfig(url=v)
        return v

    @field_validator(
        "workday_companies",
        "greenhouse_companies",
        "lever_companies",
        "ashby_companies",
        mode="before",
    )
    @classmethod
    def _parse_company_csv(cls, v: object) -> list[str] | None:
        """Accept CSV (`anthropic,openai`) from env vars; trim + drop blanks."""
        if v is None or v == "":
            return None
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v  # type: ignore[return-value]

    # Boot-time debug flag. Read from `NAAVIK_DEBUG` only (no generic `DEBUG`
    # alias per PR #49 hacker review — `DEBUG=1` is shared by Flask/Django and
    # would silently disable PC.5's SECRET_KEY validator). Production
    # (`docker compose up` / NixOS module) leaves it unset.
    debug: bool = Field(
        default=False,
        validation_alias="NAAVIK_DEBUG",
    )

    # Plan 17 (PC.5, 2026-05-16): boot-time enforcement of SECRET_KEY rules.
    # Refuse the shipped default + reject keys shorter than 32 bytes UNLESS
    # Settings.debug is True (i.e. NAAVIK_DEBUG=1). 32 bytes ≈ 256 bits of
    # entropy, matches OWASP guidance for HS256 JWT signing keys.
    @model_validator(mode="after")
    def _enforce_secret_key(self) -> "Settings":
        if self.debug:
            return self
        if self.secret_key == "change-me-in-production":
            raise ValueError(
                "SECRET_KEY is set to the shipped default 'change-me-in-production'. "
                "Set it to a random 32+ byte string before running outside of dev. "
                "To run with the default in dev, set NAAVIK_DEBUG=1."
            )
        if len(self.secret_key.encode("utf-8")) < 32:
            raise ValueError(
                "SECRET_KEY is shorter than 32 bytes. Generate a strong key with "
                "`python -c 'import secrets; print(secrets.token_urlsafe(48))'` "
                "and set it via the SECRET_KEY env var. "
                "To bypass in dev, set NAAVIK_DEBUG=1."
            )
        return self


settings = Settings()
