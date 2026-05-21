"""Per-source proxy configuration resolver.

Per docs/design/LINKEDIN_PROXY.md § C-D (graduated from plan 64 § C-D).
`ProxyURLConfig` is the Pydantic v2 model that validates the env-loaded
proxy URL; `resolve_proxy_config(source)` returns a Crawl4AI
`ProxyConfig | None` (only LinkedIn this plan; multi-source generalization
deferred to `0.8.0.NN` follow-up).

Shape (v1):
    LINKEDIN_PROXY_URL: str | None  # http(s) | socks5; basic-auth-in-URL OK.

The env-var carries Basic-auth credentials (`user:pass@host:port`). The
`safe_proxy_host` helper strips userinfo + scheme before any log/error path
emits it so credentials never reach `JobScrapeRun.errors[]` or
`log.warning(...)`. See § G in the design doc for the secret-handling
contract.

Provider-agnostic per plan 64 § D.2: operator points the env-var at any
HTTP / HTTPS / SOCKS5 proxy URL their provider exposes (Bright Data /
Smartproxy / IPRoyal / etc.). Crawl4AI's `ProxyConfig.from_string` handles
the parsing.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from crawl4ai import ProxyConfig
from pydantic import BaseModel, ConfigDict, Field, field_validator

from models import JobSource

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)

_ALLOWED_PROXY_SCHEMES = frozenset({"http", "https", "socks5"})
_MIN_PORT, _MAX_PORT = 1, 65535


class ProxyURLConfig(BaseModel):
    """Validated proxy URL — operator-supplied env var.

    Scheme allow-list = `{http, https, socks5}`. Host must be non-empty.
    Port required + in 1-65535. Query string + fragment rejected (none of
    the supported providers expose meaningful query parameters that
    Crawl4AI's parser can consume).
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    url: str = Field(min_length=1)
    provider_hint: str | None = Field(default=None, max_length=64)

    @field_validator("url")
    @classmethod
    def _validate_url(cls, v: str) -> str:
        try:
            parts = urlsplit(v)
        except ValueError as exc:
            raise ValueError(f"unparseable proxy URL: {exc}") from exc
        scheme = parts.scheme.lower()
        if scheme not in _ALLOWED_PROXY_SCHEMES:
            raise ValueError(
                f"unsupported proxy scheme {scheme!r}; allowed: {sorted(_ALLOWED_PROXY_SCHEMES)}"
            )
        if not parts.hostname:
            raise ValueError("proxy URL missing host")
        if parts.port is None:
            raise ValueError("proxy URL missing port")
        if not (_MIN_PORT <= parts.port <= _MAX_PORT):
            raise ValueError(f"proxy URL port {parts.port} outside 1..65535")
        if parts.query:
            raise ValueError("proxy URL must not carry query string")
        if parts.fragment:
            raise ValueError("proxy URL must not carry fragment")
        # Plan 64 PR #165 delta-fix LOW-2: reject degenerate userinfo shapes
        # `user:@host:port` (empty pass) + `:pass@host:port` (empty user).
        # `urlsplit` accepts both but proxy auth requires both halves to be
        # non-empty — empty halves are an operator-misconfig footgun that
        # would otherwise reach Crawl4AI's `ProxyConfig.from_string` and
        # produce confusing 407 Auth Required errors at scrape-time.
        if parts.username is not None or parts.password is not None:
            if not parts.username:
                raise ValueError("proxy URL has empty username in userinfo")
            if not parts.password:
                raise ValueError("proxy URL has empty password in userinfo")
        return v

    def to_crawl4ai(self) -> ProxyConfig:
        """Convert to a Crawl4AI `ProxyConfig` via `ProxyConfig.from_string`."""
        return ProxyConfig.from_string(self.url)

    def __repr__(self) -> str:
        """Plan 64 PR #165 delta-fix LOW-1: redacted repr — never expose creds.

        Pydantic's default `__repr__` reproduces every field value verbatim,
        which includes the operator's `user:pass@host:port` URL. If any
        future log site does `log.warning("config: %r", cfg)` the credentials
        leak. Override to a host:port-only shape via `safe_proxy_host`.
        """
        return (
            f"ProxyURLConfig(url='{safe_proxy_host(self.url)}', "
            f"provider_hint={self.provider_hint!r})"
        )


def safe_proxy_host(url: str | None) -> str:
    """Strip userinfo + scheme; return `<host>:<port>` only.

    Used in every log line + JobScrapeRun.raw_meta write that mentions the
    proxy URL. Credentials carried in Basic-auth form (`user:pass@host:port`)
    must NEVER reach a logging path. Returns the host:port slice exclusively;
    a missing host falls back to `<no-proxy>`.
    """
    if not url:
        return "<no-proxy>"
    try:
        parts = urlsplit(url)
    except ValueError:
        return "<unparseable-proxy>"
    host = parts.hostname
    if not host:
        return "<no-proxy-host>"
    if parts.port is not None:
        return f"{host}:{parts.port}"
    return host


def resolve_proxy_config(source: JobSource) -> ProxyURLConfig | None:
    """Return the effective `ProxyURLConfig` for one source, or `None`.

    v1: only LinkedIn reads `LINKEDIN_PROXY_URL`. Other sources always
    return `None`. Multi-source generalization deferred to `0.8.0.NN`
    (see plan 64 § H).

    Returns `None` when the env-var is unset OR when the operator-supplied
    URL failed validation at app boot. (Boot-time validation is the FAIL
    LOUD path per D.6 — `config.py` raises at startup, the cron never sees
    a half-broken proxy.)
    """
    if source is not JobSource.LINKEDIN:
        return None

    # Lazy import — config.py imports models.JobSource indirectly via the
    # services layer; avoid the circular import by deferring config access
    # until call time.
    from config import settings as app_settings

    url = app_settings.linkedin_proxy_url
    if not url:
        return None

    # Validation already ran at app boot via the Settings field_validator.
    # Re-construct here for the structured shape; cheap (Pydantic v2 model
    # construction on a 100-char string).
    try:
        return ProxyURLConfig(url=url, provider_hint=app_settings.linkedin_proxy_provider_hint)
    except Exception as exc:  # noqa: BLE001 — defensive; boot validation should have caught it
        log.warning("resolve_proxy_config rejected URL: %s", safe_proxy_host(url))
        raise ValueError(
            f"LINKEDIN_PROXY_URL re-validation failed for proxy={safe_proxy_host(url)}"
        ) from exc


__all__ = ["ProxyURLConfig", "resolve_proxy_config", "safe_proxy_host"]
