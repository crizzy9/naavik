"""Log/error-string redaction helpers used by the scraper layer.

Per `docs/design/SCRAPER_BASE.md` § H.4. Both `scraper_service.run_scraper`
(writes `JobScrapeRun.errors[]`) and `crawl4ai_client.{fetch_html,
stream_many}` (writes `log.warning`) route URL + exception material through
`safe_url` + `safe_exc` before persisting or logging. `safe_msg` (plan 32)
parallels `safe_exc` for raw upstream-message strings (Crawl4AI's
`result.error_message`) that don't carry a class-name prefix.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

_MAX_EXC_MSG_LEN = 200
_ALLOWED_SCHEMES = frozenset({"http", "https"})

# ANSI CSI: ESC '[' params intermediates final-byte. Covers SGR (e.g. \x1b[31m),
# cursor moves, mode sets. Standard grammar per ECMA-48.
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
# C0 controls except \t (0x09) and \n (0x0a); plus DEL (0x7f). \r is dropped
# because CRLF in log strings breaks downstream parsers + shippers.
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def _strip_control_chars(s: str) -> str:
    """Drop ANSI escape sequences + C0 controls + DEL; preserve \\t and \\n."""
    return _CONTROL_CHARS_RE.sub("", _ANSI_ESCAPE_RE.sub("", s))


def safe_url(url: str | None) -> str:
    """Strip query string + fragment + Basic-auth userinfo; preserve scheme + host + path.

    Returns `"<no-url>"` for None / empty input. Non-http(s) schemes return
    `"<scheme-blocked: {scheme} '{path}'>"` so forensics keeps the offending
    input visible without dereferencing risk.

    Plan 64 § D.8: also strips the `user:pass@` userinfo segment of the
    AUTHORITY. Prior to plan 64 `safe_url` preserved `netloc` verbatim, which
    leaked `LINKEDIN_PROXY_URL` credentials into log lines + `JobScrapeRun.errors[]`
    when a proxy-tunneled URL flowed through it. Userinfo strip is now the
    chokepoint regardless of caller (no separate `safe_proxy_host` required for
    pass-through URLs).
    """
    if not url:
        return "<no-url>"
    try:
        parts = urlsplit(url)
    except ValueError:
        return "<unparseable-url>"
    scheme = parts.scheme.lower()
    if scheme and scheme not in _ALLOWED_SCHEMES:
        return f"<scheme-blocked: {scheme} '{parts.path}'>"
    # Reconstruct netloc without userinfo (drop `user:pass@`). `parts.hostname`
    # + `parts.port` preserve IPv6-bracketed hosts (`[::1]:80`) correctly.
    host = parts.hostname or ""
    if parts.port is not None:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, parts.path, "", ""))


def safe_exc(exc: BaseException) -> str:
    """Format `<ClassName>: <truncated-msg>` capped at 200 message chars.

    Drops `__traceback__`, `args` tuple, `__cause__`. Class name preserved
    intact so operator grep stays useful; message slice prevents secret-leak
    from `f"{exc!s}"` dumps of SQL rows / request bodies / 4xx HTML pages.
    ANSI escapes + C0 controls + DEL stripped via `_strip_control_chars` so
    log shippers + the `0.2.0.11` operator UI render cleanly.
    """
    msg = _strip_control_chars(str(exc))[:_MAX_EXC_MSG_LEN]
    return f"{type(exc).__name__}: {msg}"


def safe_msg(msg: str | None) -> str:
    """Truncate a free-form upstream message to 200 chars; strip non-printables.

    Used for Crawl4AI's `result.error_message` and any other untrusted
    upstream string that lands in `log.warning` or `JobScrapeRun.errors[]`.
    Parallels `safe_exc` shape — same 200-char cap, same C0/DEL/ANSI strip —
    but without the `<ClassName>:` prefix since the upstream string has no
    structured shape.
    """
    if not msg:
        return "<no-msg>"
    return _strip_control_chars(msg)[:_MAX_EXC_MSG_LEN]
