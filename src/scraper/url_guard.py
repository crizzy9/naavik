"""URL-composition safety guards used by per-site scraper subclasses.

Per docs/design/SCRAPER_SITES.md § D.5 (graduated from plan 33). Closes the
two URL-composer-layer forward refs cataloged in
docs/plans/archive/32-0.2.0.06b-scraper-hardening-r2.md:228-234.

Two threats motivate this module:

1. **Userinfo injection** — `https://user:pass@host/path` parses as a valid
   `HttpUrl` but leaks basic-auth credentials to the target host if any
   user-controlled value composed the URL.

2. **SSRF to internal networks** — RFC1918 / IMDS / link-local destinations
   serve internal services (cloud metadata, kubernetes API servers, dev DBs).
   Resolve the destination host + reject if the resolved IP lands in:
   - 127.0.0.0/8 (loopback) — allowed in `Settings.debug=True` for localhost dev
   - 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16 (RFC1918)
   - 169.254.0.0/16 (link-local + AWS IMDS at 169.254.169.254)
   - 0.0.0.0/8 (any-address)
   - ::1/128 + fe80::/10 + fc00::/7 (IPv6 loopback / link-local / ULA)

The guard is called at URL-composition time (in the subclass), not fetch
time, so user-controlled inputs are rejected before they reach
`Crawl4AIClient`. `Crawl4AIClient.fetch_html` + `stream_many` ALSO call this
guard as a defense-in-depth layer so a future scraper that forgets to call
it still gets blocked.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
from urllib.parse import urlsplit

from cachetools import TTLCache

from config import settings as _settings

log = logging.getLogger(__name__)

_DENY_NETWORKS_V4: tuple[ipaddress.IPv4Network, ...] = (
    ipaddress.IPv4Network("10.0.0.0/8"),
    ipaddress.IPv4Network("172.16.0.0/12"),
    ipaddress.IPv4Network("192.168.0.0/16"),
    ipaddress.IPv4Network("169.254.0.0/16"),
    ipaddress.IPv4Network("127.0.0.0/8"),
    ipaddress.IPv4Network("0.0.0.0/8"),
)
_DENY_NETWORKS_V6: tuple[ipaddress.IPv6Network, ...] = (
    ipaddress.IPv6Network("::1/128"),
    ipaddress.IPv6Network("fe80::/10"),
    ipaddress.IPv6Network("fc00::/7"),
)
_ALLOWED_SCHEMES = frozenset({"http", "https"})
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


# Bounded TTL DNS cache (plan 38 § D.6; closes 0.2.0.13a Issue #105). 60s TTL
# bounds the DNS-rebind TOCTOU window to <=60s; LRU eviction at 256 entries
# matches the per-process cron load (~100 listings/hour, far fewer hosts).
# Single-process + single-asyncio-loop usage today; if multi-process workers
# ship in Phase 2+, add a `threading.Lock` around get/set.
# TODO(0.2.0.NN): wrap _DNS_CACHE access in threading.Lock when multi-worker
# scrape orchestration ships. cachetools.TTLCache is not thread-safe.
_DNS_CACHE: TTLCache[str, tuple[str, ...]] = TTLCache(maxsize=256, ttl=60.0)


def _resolve_host(host: str) -> tuple[str, ...]:
    """DNS resolution with bounded-TTL cache.

    Returns a tuple of resolved IP strings (deduplicated). Empty tuple on
    `gaierror` so the caller can reject explicitly rather than accept by
    default. Re-resolves every 60s per host to bound the rebind window.
    """
    cached = _DNS_CACHE.get(host)
    if cached is not None:
        return cached
    try:
        info = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        log.debug("DNS resolution failed: host=%s err=%s", host, exc)
        return ()
    addrs = tuple({addr[4][0] for addr in info})
    _DNS_CACHE[host] = addrs
    return addrs


def is_safe_destination(url: str) -> tuple[bool, str | None]:
    """Return `(True, None)` on safe URLs; `(False, reason)` on rejected.

    Four classes of rejection:

    1. Unparseable URL → `"unparseable_url"`.
    2. Scheme is not http(s) → `"scheme_not_allowed:<scheme>"`. Mirrors
       `Crawl4AIClient`'s `HttpUrl` validation so scrapers get the same
       answer from either layer.
    3. Userinfo present (`user:pass@host`) → `"userinfo_present"`.
    4. Hostname missing → `"invalid_host"`.
    5. Resolved IP in deny-network → `"private_destination:<ip>"`.

    `Settings.debug=True` (dev orchestrator) allows `localhost` /
    `127.0.0.1` / `::1`; RFC1918, IMDS, link-local, IPv6 ULA remain blocked
    in debug too — only the bare-loopback escape hatch flips.

    Pure function; safe to call inside exception handlers.
    """
    try:
        parts = urlsplit(url)
    except ValueError:
        return False, "unparseable_url"
    scheme = parts.scheme.lower()
    if scheme and scheme not in _ALLOWED_SCHEMES:
        return False, f"scheme_not_allowed:{scheme}"
    if parts.username or parts.password:
        return False, "userinfo_present"
    host = parts.hostname
    if not host:
        return False, "invalid_host"
    # Localhost dev escape hatch (gated on NAAVIK_DEBUG=1).
    if _settings.debug and host in _LOOPBACK_HOSTS:
        return True, None
    addrs = _resolve_host(host)
    if not addrs:
        return False, "dns_resolution_failed"
    for addr_str in addrs:
        try:
            addr = ipaddress.ip_address(addr_str)
        except ValueError:
            continue
        if isinstance(addr, ipaddress.IPv4Address):
            for net in _DENY_NETWORKS_V4:
                if addr in net:
                    return False, f"private_destination:{addr_str}"
        elif isinstance(addr, ipaddress.IPv6Address):
            for net in _DENY_NETWORKS_V6:
                if addr in net:
                    return False, f"private_destination:{addr_str}"
    return True, None


# Plan 43 (`0.2.0.07a`) — slug regex for operator-supplied URL components.
# Closes PR #102 hacker MEDIUMs (#103): Workday tenant-fragment trick
# (`tenant="evil.com#"` bypasses `is_safe_destination` via `urlsplit.hostname`
# returning `evil.com`) + Lever path-position substitution (`company="acme/..
# /v0/users/{id}"` smuggles vendor API path traversal). Slug-validate BEFORE
# template substitution; rejects all confusable shapes catalogued in plan 43
# § D.1 (empty / leading hyphen / fragment / query / `@` / `/` / whitespace /
# null / newline / dot / URL-as-slug).
_SLUG_RE: re.Pattern[str] = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")


class InvalidSlugError(ValueError):
    """Raised by `_make_url` when a slug kwarg fails `_SLUG_RE`.

    Subclass of `ValueError` so callers using broad `except ValueError:` or
    `except Exception:` keep composing. Carries `slug_name` + `value` for
    log redaction.
    """

    def __init__(self, slug_name: str, value: str) -> None:
        super().__init__(f"invalid_slug:{slug_name}={value!r}")
        self.slug_name = slug_name
        self.value = value


def _make_url(template: str, **slugs: str) -> str:
    """Format `template` with slug-validated kwargs.

    Each kwarg value is matched against `_SLUG_RE` BEFORE substitution; first
    failure raises `InvalidSlugError(slug_name, value)`. Composes with
    `is_safe_destination` — callers run both: this helper closes the
    composition-bug vector, `is_safe_destination` closes the DNS-resolution
    one.
    """
    for name, value in slugs.items():
        if not isinstance(value, str) or not _SLUG_RE.match(value):
            raise InvalidSlugError(name, value if isinstance(value, str) else str(value))
    return template.format(**slugs)
