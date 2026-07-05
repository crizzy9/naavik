"""IMAP host SSRF guard — plan 90 / 0.5.0.01 (PR #214 hacker H1 fold-in).

A user-supplied `imap_host:port` is a server-side request target: the sync
cron + the connect/test routes open a TCP connection to whatever the user
typed. With open signup, any user could point that at an internal target
(AWS IMDS `169.254.169.254`, loopback Ollama/Postgres, the app itself) and
use the reflected connection error as a service-discovery oracle.

This mirrors the existing scraper guard `src/scraper/url_guard.is_safe_destination`
posture exactly:

- Resolve the host (bounded-TTL DNS cache; re-resolve every 60s to cap the
  DNS-rebind TOCTOU window) and DENY if any resolved IP lands in the private
  IPv4 ranges (`10/8`, `172.16/12`, `192.168/16`, `169.254/16` incl. IMDS,
  `127/8` loopback, `0/8` any) or the IPv6 ranges (`::1/128`, `fe80::/10`,
  `fc00::/7` ULA).
- Enforce a port allowlist of `{143, 993}` (standard IMAP / IMAPS).
- Fail CLOSED — a resolution failure DENIES (never accept-by-default).
- `Settings.debug=True` (dev orchestrator) opens a loopback-only escape hatch
  so the owner can test against a local mail server; RFC1918 / IMDS / ULA stay
  blocked even in debug, exactly like `url_guard`.

The guard is called at every connection point (connect route + test route +
sync_account `_runner` driving the cron) so a TOCTOU rebind between connect
and a later sync is re-checked, not trusted once.
"""

from __future__ import annotations

import ipaddress
import logging
import socket

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
_ALLOWED_PORTS = frozenset({143, 993})
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

# Canonical client-facing message — never reveals whether an internal target
# exists/listens, so it can't be used as a service-discovery oracle.
SAFE_ERROR_MESSAGE = "That mail server host or port is not permitted."

# Bounded TTL DNS cache mirrors url_guard's: 60s TTL caps the rebind window;
# LRU eviction at 256 entries. Single-process + single-loop usage today.
_DNS_CACHE: TTLCache[str, tuple[str, ...]] = TTLCache(maxsize=256, ttl=60.0)


class ImapHostNotAllowed(ValueError):
    """Raised by `ensure_imap_host_allowed` when (host, port) is denied.

    Subclass of `ValueError` so callers using broad `except ValueError:` keep
    composing. Carries `reason` (e.g. `private_destination:10.0.0.5`) for
    server-side logging only — never surfaced to the client.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _resolve_host(host: str) -> tuple[str, ...]:
    """DNS resolution with bounded-TTL cache.

    Returns a tuple of resolved IP strings (deduplicated). Empty tuple on
    failure so the caller rejects explicitly rather than accept by default.
    """
    cached = _DNS_CACHE.get(host)
    if cached is not None:
        return cached
    try:
        info = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        log.debug("imap_host_guard: DNS resolution failed host=%s err=%s", host, exc)
        return ()
    addrs = tuple({addr[4][0] for addr in info})
    _DNS_CACHE[host] = addrs
    return addrs


def check_imap_host(host: str, port: int) -> tuple[bool, str | None]:
    """Return `(True, None)` on safe; `(False, reason)` on rejected.

    Rejection classes (reason strings are for server-side logs only):
    - `port_not_allowed:<port>` — port outside `{143, 993}`.
    - `invalid_host` — empty/blank host.
    - `dns_resolution_failed` — host does not resolve (fail closed).
    - `private_destination:<ip>` — a resolved IP is in a deny-network.

    `Settings.debug=True` allows the bare loopback hosts; RFC1918, IMDS,
    link-local and IPv6 ULA remain blocked in debug too.

    Pure function; safe to call inside exception handlers.
    """
    if port not in _ALLOWED_PORTS:
        return False, f"port_not_allowed:{port}"
    host = (host or "").strip()
    if not host:
        return False, "invalid_host"
    # IPv6 literals may arrive bracketed (`[::1]`); imaplib takes them bare,
    # but normalize so getaddrinfo + the denylist see the address.
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
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


def ensure_imap_host_allowed(host: str, port: int) -> None:
    """Raise `ImapHostNotAllowed(reason)` when (host, port) is denied.

    Logs the denial reason server-side; the raised exception carries the
    reason for logs only. Callers surface `SAFE_ERROR_MESSAGE` to the client.
    """
    safe, reason = check_imap_host(host, port)
    if not safe:
        log.warning("imap_host_guard: rejected host=%r port=%s reason=%s", host, port, reason)
        raise ImapHostNotAllowed(reason or "rejected")
