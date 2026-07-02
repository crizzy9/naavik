"""Env-presence indicators — post-vault replacement for `Settings.*_configured`.

Per ROADMAP row 0.2.0.01 (plan 26): the 5 `Settings._configured` boolean
columns + `Settings.llm_api_key_fingerprint` are dropped. Settings UI +
API surfaces still need to render "Anthropic: configured via env ✓ / ✗"
indicators without exposing values.

Each helper reads `config.settings` (pydantic-settings already loads from
`.env` + actual env). Empty / None means absent; non-empty means present.
NEVER returns the value itself; the caller cannot leak.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from config import Settings as AppSettings
from config import settings as app_settings
from models.enums import ApplicationBoard, JobSource, LLMProvider

if TYPE_CHECKING:
    from models import Settings


# Plan 63 / 0.2.7.10 § D.3 — env-slot mapping per ATS board. Adapter
# implementations land in 0.4.0.NN (Workday) + 0.8.0.NN (LinkedIn/Indeed/Generic);
# the env slots are reserved + presence-rendered in Settings · Submissions today.
# COMPANY_DIRECT (Generic) is operator-tunable via `ats_generic_llm_confidence_threshold`
# (default 0.7); not a credential, so it's not in this presence map.
_ATS_BOARD_ENV_SLOT: dict[ApplicationBoard, str] = {
    ApplicationBoard.WORKDAY: "WORKDAY_LOGIN_TOKEN",
    ApplicationBoard.LINKEDIN: "LINKEDIN_SESSION_COOKIE",
    ApplicationBoard.INDEED: "INDEED_SESSION_COOKIE",
}

# Phase-chip text rendered alongside each presence indicator in the
# Settings · Submissions panel. Flips to "Available" when the per-adapter PR
# merges; the value here is the source-of-truth for the chip.
_ATS_BOARD_PHASE: dict[ApplicationBoard, str] = {
    ApplicationBoard.WORKDAY: "Phase 4+",
    ApplicationBoard.LINKEDIN: "Phase 5+",
    ApplicationBoard.INDEED: "Phase 5+",
    ApplicationBoard.COMPANY_DIRECT: "Phase 5+",
}


def llm_provider_configured(provider: LLMProvider) -> bool:
    """True iff an API key is set in env for the given provider.

    Ollama returns True iff `OLLAMA_BASE_URL` is non-empty (default
    `http://localhost:11434` is always set, so effectively always True —
    the indicator follows the same shape as Anthropic/OpenAI for UI uniformity).
    """
    if provider is LLMProvider.ANTHROPIC:
        return bool(app_settings.anthropic_api_key)
    if provider is LLMProvider.OPENAI:
        return bool(app_settings.openai_api_key)
    if provider is LLMProvider.OLLAMA:
        return bool(app_settings.ollama_base_url)
    return False


def discord_webhook_configured() -> bool:
    return bool(app_settings.discord_webhook_url)


def telegram_bot_configured() -> bool:
    return bool(app_settings.telegram_bot_token) and bool(app_settings.telegram_chat_id)


def portfolio_webhook_configured() -> bool:
    return bool(app_settings.portfolio_webhook_url)


def env_indicators_for_llm_tab() -> dict[str, bool]:
    """Bundle for `_settings_llm.html` template context."""
    return {
        "anthropic": llm_provider_configured(LLMProvider.ANTHROPIC),
        "openai": llm_provider_configured(LLMProvider.OPENAI),
        "ollama": llm_provider_configured(LLMProvider.OLLAMA),
    }


def resolve_active_llm_provider(settings: AppSettings | None = None) -> str | None:
    """Pick the active LLM provider by env-presence precedence.

    Plan 70 (0.3.3.13): Settings · LLM tab dual-selector cleanup. The
    explicit "Active provider" radio surface is deleted; the active
    provider is implicit-by-env. Precedence: ANTHROPIC > OPENAI > OLLAMA.
    Returns `None` only when no provider key is set (Ollama defaults to
    `http://localhost:11434` so the trailing branch always fires in dev).

    `settings` is the pydantic-settings `config.Settings` (env reads), NOT
    the per-user `models.Settings`. Default to the module-level singleton
    so tests can monkeypatch the same `app_settings` they patch elsewhere.
    """
    s = settings if settings is not None else app_settings
    if s.anthropic_api_key:
        return "anthropic"
    if s.openai_api_key:
        return "openai"
    if s.ollama_base_url:
        return "ollama"
    return None


def env_indicators_for_notifications_tab() -> dict[str, bool]:
    return {
        "discord": discord_webhook_configured(),
        "telegram": telegram_bot_configured(),
        "portfolio": portfolio_webhook_configured(),
    }


def scraper_source_configured(source: JobSource, settings: Settings, profile=None) -> bool:
    """True iff the source has the operator-facing config it needs to scrape.

    Per plan 49 / 0.2.0.16 § D.3 + docs/design/JOB_SEARCH_PREFERENCES.md.
    Composition:
    - Company-list sources (Workday / Greenhouse / Lever / Ashby): configured
      iff their env-var watchlist is non-empty (Workday reads
      `Settings.workday_companies`; the other three read env-loaded config).
    - Keyword sources (LinkedIn / Indeed): configured iff the profile has
      `target_titles` OR a per-source Settings keyword override is set.
    - Other sources (COMPANY_DIRECT / RSSHUB / N8N_LEGACY / MANUAL): not
      surfaced on the Sources panel; returns False.
    """
    if source is JobSource.WORKDAY:
        return bool(settings.workday_companies)
    if source is JobSource.GREENHOUSE:
        return bool(app_settings.greenhouse_companies)
    if source is JobSource.LEVER:
        return bool(app_settings.lever_companies)
    if source is JobSource.ASHBY:
        return bool(app_settings.ashby_companies)
    profile_titles = bool(getattr(profile, "target_titles", None))
    if source is JobSource.LINKEDIN:
        return bool(getattr(settings, "linkedin_keywords", None)) or profile_titles
    if source is JobSource.INDEED:
        return bool(getattr(settings, "indeed_keywords", None)) or profile_titles
    return False


def workday_credential_env_present() -> bool:
    """True iff `WORKDAY_LOGIN_TOKEN` is set in env."""
    return bool(app_settings.workday_login_token)


def linkedin_session_cookie_env_present() -> bool:
    """True iff `LINKEDIN_SESSION_COOKIE` is set in env."""
    return bool(app_settings.linkedin_session_cookie)


def linkedin_proxy_configured() -> bool:
    """True iff `LINKEDIN_PROXY_URL` is set in env (plan 64 / 0.2.7.11).

    Surface only — never returns the URL value. UI renders a "configured"
    chip + the redacted host (`gate.smartproxy.com:7000`); userinfo never
    reaches the template context. See `safe_proxy_host` in `scraper.proxy`.
    """
    return bool(app_settings.linkedin_proxy_url)


def linkedin_proxy_host_redacted() -> str | None:
    """Return the proxy `<host>:<port>` (no userinfo), or `None` when unset.

    Plan 64 § G.1: the host is not a secret (operators see it on every
    provider dashboard); userinfo IS the secret. `safe_proxy_host` strips
    userinfo + scheme. Used by the Sources UI to render "Proxy via
    gate.smartproxy.com:7000" without leaking creds.
    """
    url = app_settings.linkedin_proxy_url
    if not url:
        return None
    from scraper.proxy import safe_proxy_host

    return safe_proxy_host(url)


def indeed_credential_env_present() -> bool:
    """True iff `INDEED_SESSION_COOKIE` is set in env."""
    return bool(app_settings.indeed_session_cookie)


def ats_credential_env_present(board: ApplicationBoard) -> bool:
    """Dispatch helper — env-presence per ATS board (credentials only).

    Per plan 63 § C.6. Returns False for COMPANY_DIRECT (the Generic adapter
    is operator-tuned via threshold, not a credential) and for unknown /
    unhandled board (typo guard, mirrors `scraper_source_configured` shape).
    """
    if board is ApplicationBoard.WORKDAY:
        return workday_credential_env_present()
    if board is ApplicationBoard.LINKEDIN:
        return linkedin_session_cookie_env_present()
    if board is ApplicationBoard.INDEED:
        return indeed_credential_env_present()
    return False


def ats_credential_indicators() -> list[dict[str, object]]:
    """Settings · Submissions panel context bundle.

    Per plan 63 § C.6. Three credential rows (Workday / LinkedIn / Indeed)
    + one tunable row (Generic threshold). Each credential entry:
    `{board, env_var, configured, phase, kind: "credential"}`. The tunable
    entry: `{board, env_var, value, phase, kind: "tunable"}`. The UI partial
    renders a read-only table; secret entry stays in `.env` per the
    post-vault pattern. Per-adapter PR (0.4.0.NN / 0.8.0.NN) flips each
    board's `phase` chip to "Available" when the adapter ships.
    """
    rows: list[dict[str, object]] = [
        {
            "board": board,
            "env_var": _ATS_BOARD_ENV_SLOT[board],
            "configured": ats_credential_env_present(board),
            "phase": _ATS_BOARD_PHASE[board],
            "kind": "credential",
        }
        for board in (
            ApplicationBoard.WORKDAY,
            ApplicationBoard.LINKEDIN,
            ApplicationBoard.INDEED,
        )
    ]
    rows.append(
        {
            "board": ApplicationBoard.COMPANY_DIRECT,
            "env_var": "ATS_GENERIC_LLM_CONFIDENCE_THRESHOLD",
            "value": app_settings.ats_generic_llm_confidence_threshold,
            "phase": _ATS_BOARD_PHASE[ApplicationBoard.COMPANY_DIRECT],
            "kind": "tunable",
        }
    )
    return rows


def is_configured(scope: str) -> bool:
    """Generic scope-based lookup.

    Accepts any of the canonical UI / API scope names: `anthropic`,
    `openai`, `ollama`, `discord`, `telegram`, `portfolio`. Returns False
    on unknown scope (caller-facing typo guard).
    """
    if scope == "anthropic":
        return llm_provider_configured(LLMProvider.ANTHROPIC)
    if scope == "openai":
        return llm_provider_configured(LLMProvider.OPENAI)
    if scope == "ollama":
        return llm_provider_configured(LLMProvider.OLLAMA)
    if scope == "discord":
        return discord_webhook_configured()
    if scope == "telegram":
        return telegram_bot_configured()
    if scope == "portfolio":
        return portfolio_webhook_configured()
    return False
