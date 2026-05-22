"""Regression lint: no direct HTTP libs inside `src/scraper/`.

Per plan 33 § D.9 / `docs/design/SCRAPER_BASE.md § Cross-cutting context`.
All URL fetches must flow through `Crawl4AIClient` so `pydantic.HttpUrl`
validation + rate-limit hooks + Crawl4AI stealth + the URL guard apply
uniformly. This lint catches accidental shortcuts.

Plan 46 / 0.2.0.07b widened the guard from set-membership to prefix-match
+ added the `urllib.*` / `http.*` / `aiohttp.*` namespaces + sibling libs
(`urllib3` / `httpcore` / `niquests`) that pre-2026-05-20 slipped past.

Allowlist:
- `src/scraper/url_guard.py` uses `socket.getaddrinfo` (DNS only — not
  an HTTP fetch).
- `urllib.parse` is the URL-component / query-string helper used by the
  URL guard and is NOT an HTTP client; explicit whitelist.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.uses_sample_data_shims

FORBIDDEN_PREFIXES = (
    "requests",
    "httpx",
    "urllib",
    "urllib3",
    "http.client",
    "httpcore",
    "niquests",
    "aiohttp",
)
WHITELIST_EXACT = frozenset(
    {
        # Not an HTTP client — URL-component helpers used by url_guard.
        "urllib.parse",
    }
)
SCRAPER_DIR = Path(__file__).parent.parent / "src" / "scraper"


def _is_forbidden(module_name: str | None) -> bool:
    """Prefix-match against FORBIDDEN_PREFIXES with WHITELIST_EXACT escape.

    `module_name` is the dotted import path (`urllib.request`,
    `aiohttp.client`, `http.client`, ...). A name matches a prefix when
    it equals the prefix OR starts with `<prefix>.`. The whitelist takes
    precedence so legitimate `urllib.parse` imports stay legal.
    """
    if module_name is None:
        return False
    if module_name in WHITELIST_EXACT:
        return False
    for prefix in FORBIDDEN_PREFIXES:
        if module_name == prefix or module_name.startswith(prefix + "."):
            return True
    return False


def _walk_offenders(tree: ast.AST, source_path: Path) -> list[str]:
    """Return one offense string per forbidden import in `tree`.

    Walks both `ast.Import` (e.g. `import urllib3`, `import http.client`)
    and `ast.ImportFrom` (e.g. `from urllib import request`,
    `from aiohttp.client import ClientSession`).
    """
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_forbidden(alias.name):
                    offenders.append(f"{source_path}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom) and _is_forbidden(node.module):
            offenders.append(f"{source_path}: from {node.module} import ...")
    return offenders


def test_no_direct_http_imports_in_scraper_layer():
    offending: list[str] = []
    for py_file in SCRAPER_DIR.rglob("*.py"):
        tree = ast.parse(py_file.read_text())
        offending.extend(_walk_offenders(tree, py_file))
    assert not offending, "Direct HTTP imports found:\n" + "\n".join(offending)


# ── _is_forbidden helper coverage ────────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        "requests",
        "httpx",
        "httpx.AsyncClient",
        "urllib",
        "urllib.request",
        "urllib3",
        "http.client",
        "httpcore",
        "niquests",
        "aiohttp",
        "aiohttp.client",
    ],
)
def test_forbidden_prefixes_rejected(name: str) -> None:
    """Each canonical HTTP-client form trips the prefix-match guard."""
    assert _is_forbidden(name) is True


@pytest.mark.parametrize(
    "name",
    [
        "urllib.parse",  # whitelisted — URL component helper, not an HTTP client
        "typing",
        "pathlib",
        "asyncio",
        "json",
        "socket",  # url_guard uses socket.getaddrinfo for DNS only
        None,
    ],
)
def test_allowed_imports_passthrough(name: str | None) -> None:
    """Whitelist + unrelated imports do NOT trip the guard."""
    assert _is_forbidden(name) is False


# ── AST walk coverage (synthetic source fixtures) ────────────────────────


def _parse(source: str) -> ast.AST:
    return ast.parse(source)


def test_ast_walk_catches_plain_import_urllib3():
    """`import urllib3` (sibling lib pre-2026-05-20 missed by set-membership)."""
    offenders = _walk_offenders(_parse("import urllib3\n"), Path("synthetic.py"))
    assert len(offenders) == 1
    assert "urllib3" in offenders[0]


def test_ast_walk_catches_from_urllib_import_request():
    """`from urllib import request` — pre-prefix-match path missed this."""
    offenders = _walk_offenders(_parse("from urllib import request\n"), Path("synthetic.py"))
    assert len(offenders) == 1
    assert "from urllib import" in offenders[0]


def test_ast_walk_catches_import_http_client():
    """`import http.client` (stdlib HTTP client)."""
    offenders = _walk_offenders(_parse("import http.client\n"), Path("synthetic.py"))
    assert len(offenders) == 1


def test_ast_walk_catches_from_aiohttp_client_import():
    """Attribute-form ImportFrom — `from aiohttp.client import ClientSession`."""
    offenders = _walk_offenders(
        _parse("from aiohttp.client import ClientSession\n"),
        Path("synthetic.py"),
    )
    assert len(offenders) == 1


def test_ast_walk_allows_urllib_parse():
    """The URL-component helper is whitelisted."""
    offenders = _walk_offenders(
        _parse("from urllib.parse import urlparse, quote\n"),
        Path("synthetic.py"),
    )
    assert offenders == []


def test_ast_walk_allows_typing_imports():
    """Unrelated imports do not trip the guard."""
    offenders = _walk_offenders(
        _parse("from typing import TYPE_CHECKING\nimport asyncio\nimport json\n"),
        Path("synthetic.py"),
    )
    assert offenders == []
