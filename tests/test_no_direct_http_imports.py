"""Regression lint: no direct HTTP libs inside `src/scraper/`.

Per plan 33 § D.9 / `docs/design/SCRAPER_BASE.md § Cross-cutting context`.
All URL fetches must flow through `Crawl4AIClient` so `pydantic.HttpUrl`
validation + rate-limit hooks + Crawl4AI stealth + the URL guard apply
uniformly. This lint catches accidental shortcuts.

Allowlist: `src/scraper/url_guard.py` (`socket.getaddrinfo` is intentional +
safe; DNS resolution is not an HTTP fetch).
"""

from __future__ import annotations

import ast
from pathlib import Path

FORBIDDEN_MODULES = {"requests", "httpx", "urllib.request", "aiohttp"}
SCRAPER_DIR = Path(__file__).parent.parent / "src" / "scraper"


def test_no_direct_http_imports_in_scraper_layer():
    offending: list[str] = []
    for py_file in SCRAPER_DIR.rglob("*.py"):
        tree = ast.parse(py_file.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in FORBIDDEN_MODULES:
                        offending.append(f"{py_file}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module in FORBIDDEN_MODULES:
                offending.append(f"{py_file}: from {node.module} import ...")
    assert not offending, "Direct HTTP imports found:\n" + "\n".join(offending)
