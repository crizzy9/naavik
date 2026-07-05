"""Shared HTML → plain-text helpers (plan 91 5.5).

Two conversion flavours were copy-pasted across the JD pipeline; this is
the single home. They are intentionally NOT unified into one function —
their outputs feed `jd_hash` / stored descriptions, so each caller keeps
the exact semantics it shipped with:

- `html_to_text` — board-API description HTML → readable text: HTML-entity
  unescape (Greenhouse double-escapes), per-node strip, 3+ newlines
  collapsed. Canonical copy formerly in `jd_enrichment`.
- `fragment_text` — scraper detail-page description fragments: bare
  `get_text("\\n").strip()`, empty → None. Formerly copied verbatim in the
  Lever / Ashby / Indeed site scrapers.
"""

from __future__ import annotations

import html as html_lib
import re

from bs4 import BeautifulSoup


def html_to_text(html: str | None) -> str:
    """Board-API description HTML → plain text (Greenhouse double-escapes)."""
    if not html:
        return ""
    unescaped = html_lib.unescape(html)
    soup = BeautifulSoup(unescaped, "html.parser")
    text = soup.get_text(separator="\n", strip=True)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def fragment_text(html: str | None) -> str | None:
    """Detail-page description fragment → text; empty results become None."""
    if not html:
        return None
    return BeautifulSoup(html, "html.parser").get_text("\n").strip() or None
