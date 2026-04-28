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
    portfolio_webhook_url: str | None = None

    # OAuth (optional)
    google_client_id: str | None = None
    google_client_secret: str | None = None

    # Server
    host: str = "0.0.0.0"
    port: int = 8000


settings = Settings()
