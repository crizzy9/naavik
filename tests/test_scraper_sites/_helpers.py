"""Test helpers for site-scraper suites (plan 33 § D.8).

`FakeClient` stands in for `Crawl4AIClient` so tests don't launch Chromium +
don't depend on the URL guard's DNS. Per-URL responses are keyed by URL
prefix so tests can wire up listing + detail with one fixture each.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "html" / "sites"


def load_fixture(name: str) -> str:
    """Return the text contents of `tests/fixtures/html/sites/<name>`."""
    return (_FIXTURES_DIR / name).read_text()


class FakeClient:
    """Drop-in for `Crawl4AIClient`.

    Configure via:
      - `responses`: dict[str, str | None] keyed by exact URL or URL prefix.
        Longest prefix match wins; `None` value signals a non-fatal fetch
        failure (mirrors `Crawl4AIClient.fetch_html` returning None).
      - `raise_for_url`: dict[str, Exception] — raise the exception on that URL
        (for tier-2 failure tests).
    """

    def __init__(
        self,
        *,
        responses: dict[str, str | None] | None = None,
        raise_for_url: dict[str, Exception] | None = None,
    ) -> None:
        self.responses: dict[str, str | None] = responses or {}
        self.raise_for_url: dict[str, Exception] = raise_for_url or {}
        self.fetch_calls: list[str] = []
        self.stream_calls: list[list[str]] = []

    def _lookup(self, url: str) -> str | None:
        if url in self.responses:
            return self.responses[url]
        # Longest-prefix match — useful when only the base URL is stable.
        best: tuple[int, str | None] = (-1, None)
        for key, value in self.responses.items():
            if url.startswith(key) and len(key) > best[0]:
                best = (len(key), value)
        return best[1]

    async def fetch_html(self, url: str) -> str | None:
        self.fetch_calls.append(url)
        if url in self.raise_for_url:
            raise self.raise_for_url[url]
        for prefix, exc in self.raise_for_url.items():
            if url.startswith(prefix):
                raise exc
        return self._lookup(url)

    async def stream_many(self, urls: list[str]) -> AsyncIterator[tuple[str, str | None]]:
        self.stream_calls.append(list(urls))
        for url in urls:
            yield url, self._lookup(url)
