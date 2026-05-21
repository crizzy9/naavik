"""Log/error-string redaction helpers used by the scraper layer.

Per `docs/design/SCRAPER_BASE.md` § H.4. Both `scraper_service.run_scraper`
(writes `JobScrapeRun.errors[]`) and `crawl4ai_client.{fetch_html,
stream_many}` (writes `log.warning`) route URL + exception material through
`safe_url` + `safe_exc` before persisting or logging. `safe_msg` (plan 32)
parallels `safe_exc` for raw upstream-message strings (Crawl4AI's
`result.error_message`) that don't carry a class-name prefix.

Plan 64 PR #165 delta-fix (hacker REQUEST_CHANGES, HIGH-1 / HIGH-2 / MED):
`safe_msg` now URL-strips embedded URL-shaped substrings via `safe_url` so
proxy credentials carried in exception messages (e.g. httpx `ProxyError(
"connect to https://user:pass@proxy:8080 failed")`) cannot leak when the
free-text string is logged. `safe_exc` walks the chained-exception graph
(`__cause__` + `__context__`, depth-limited) and applies the URL-strip to
each level's message so chained transport errors don't bypass the guard.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

_MAX_EXC_MSG_LEN = 200
_MAX_CHAIN_DEPTH = 5
_MAX_SAFE_EXC_LEN = 500
_ALLOWED_SCHEMES = frozenset({"http", "https"})

# ANSI CSI: ESC '[' params intermediates final-byte. Covers SGR (e.g. \x1b[31m),
# cursor moves, mode sets. Standard grammar per ECMA-48.
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
# C0 controls except \t (0x09) and \n (0x0a); plus DEL (0x7f). \r is dropped
# because CRLF in log strings breaks downstream parsers + shippers.
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
# URL-shape substrings embedded in free-form text. Matches http(s) / socks5
# scheme + optional userinfo + host + optional port + optional path/query/frag.
# Loose by design: catches anything resembling a URL so safe_url can re-shape it.
_URL_SHAPE_RE = re.compile(
    r"\b(?:https?|socks5)://[^\s'\"<>]+",
    flags=re.IGNORECASE,
)


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


def _strip_embedded_urls(text: str) -> str:
    """Apply `safe_url` to every URL-shaped substring inside free-text.

    Plan 64 PR #165 delta-fix MED: pre-fix `safe_msg` capped + stripped control
    chars but left embedded URLs intact, so an upstream error message containing
    a credentialed proxy URL (httpx `ProxyError("connect to
    https://user:pass@host failed")`) leaked through.

    Each match is replaced with `safe_url(match)` — userinfo + query +
    fragment dropped; scheme + host + port + path preserved.
    """
    return _URL_SHAPE_RE.sub(lambda m: safe_url(m.group(0)), text)


def safe_msg(msg: str | None) -> str:
    """Truncate a free-form upstream message; strip non-printables + embedded URL creds.

    Used for Crawl4AI's `result.error_message` and any other untrusted
    upstream string that lands in `log.warning` or `JobScrapeRun.errors[]`.
    Parallels `safe_exc` shape — same 200-char cap, same C0/DEL/ANSI strip —
    but without the `<ClassName>:` prefix since the upstream string has no
    structured shape.

    Plan 64 PR #165 delta-fix MED: also URL-strips embedded URL-shaped
    substrings via `_strip_embedded_urls` so any `user:pass@` userinfo
    carried in free-text messages is redacted before the 200-char cap.
    URL-strip happens BEFORE truncation so credentials at the start of a
    long string can't survive by being past the cap.
    """
    if not msg:
        return "<no-msg>"
    return _strip_control_chars(_strip_embedded_urls(msg))[:_MAX_EXC_MSG_LEN]


def safe_exc(exc: BaseException, max_len: int = _MAX_SAFE_EXC_LEN) -> str:
    """Format `<ClassName>: <truncated-msg>` for `exc`, walking the chain.

    Drops `__traceback__` + `args` tuple but follows `__cause__` / `__context__`
    (depth-limited to 5) so chained transport errors (`raise NewError from
    OriginalProxyError`) get their original message URL-stripped too. Each
    level routes through `safe_msg` (which now URL-strips userinfo) so proxy
    credentials carried in any level's message string never reach the log
    handler.

    Plan 64 PR #165 delta-fix HIGH-2: pre-fix `safe_exc` materialized
    `str(exc)` directly. Python's `BaseException.__str__` returns the args
    joined verbatim, so a wrapped `httpx.ProxyError("connect to
    https://user:pass@host:8080 failed")` would expose `user:pass`. Now
    every level's `args[0]` (or `str()`) routes through `safe_msg` →
    `_strip_embedded_urls` → `safe_url` so userinfo is stripped.

    Output capped at `max_len` (default 500) — sufficient for 2-3 chain
    levels at ~200 chars each. Levels joined with ` caused by: ` separator.

    Backward-compatible signature: existing callers pass a single
    `BaseException` and get back a single string. Existing test
    `safe_exc(ValueError("x"*500)) == "ValueError: " + "x"*200` still
    holds because flat exceptions take the single-level path.
    """
    parts: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    depth = 0
    while current is not None and depth < _MAX_CHAIN_DEPTH:
        if id(current) in seen:
            break
        seen.add(id(current))
        msg = safe_msg(str(current))
        # safe_msg returns "<no-msg>" for empty; downgrade to "" for clean join.
        if msg == "<no-msg>":
            msg = ""
        parts.append(f"{type(current).__name__}: {msg}")
        # Prefer __cause__ (explicit `raise X from Y`) over __context__
        # (implicit during-handling-of). Both are common in transport stacks.
        current = current.__cause__ or current.__context__
        depth += 1
    joined = " caused by: ".join(parts)
    return joined[:max_len]
