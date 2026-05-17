from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
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
    portfolio_webhook_url: str | None = None

    # Data dir (mirrors production /app/.naavik in Docker, ~/.naavik on NixOS)
    data_dir: str = ".naavik"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Plan 10c (10c.3, 2026-05-11): boot-time debug flag used by the seed-time
    # `dev-credentials` file write + the FastAPI lifespan credential echo.
    # Read from `NAAVIK_DEBUG` only (no generic `DEBUG` alias per PR #49 hacker
    # review — `DEBUG=1` is shared by Flask/Django/many frameworks and would
    # silently disable PC.5's SECRET_KEY validator). Production (`docker compose
    # up` / NixOS module) leaves it unset → no dev-credentials artifacts.
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
