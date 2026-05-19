"""Log/error-string redaction helpers used by the scraper layer.

Per `docs/design/SCRAPER_BASE.md` § H.4. Both `scraper_service.run_scraper`
(writes `JobScrapeRun.errors[]`) and `crawl4ai_client.{fetch_html,
stream_many}` (writes `log.warning`) route URL + exception material through
`safe_url` + `safe_exc` before persisting or logging.
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

_MAX_EXC_MSG_LEN = 200
_ALLOWED_SCHEMES = frozenset({"http", "https"})


def safe_url(url: str | None) -> str:
    """Strip query string + fragment; preserve scheme + host + path.

    Returns `"<no-url>"` for None / empty input. Non-http(s) schemes return
    `"<scheme-blocked: {scheme} '{path}'>"` so forensics keeps the offending
    input visible without dereferencing risk.
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
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def safe_exc(exc: BaseException) -> str:
    """Format `<ClassName>: <truncated-msg>` capped at 200 message chars.

    Drops `__traceback__`, `args` tuple, `__cause__`. Class name preserved
    intact so operator grep stays useful; message slice prevents secret-leak
    from `f"{exc!s}"` dumps of SQL rows / request bodies / 4xx HTML pages.
    """
    return f"{type(exc).__name__}: {str(exc)[:_MAX_EXC_MSG_LEN]}"
