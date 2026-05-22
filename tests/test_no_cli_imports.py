"""Regression lint: no `cli` imports anywhere in `src/`.

Plan 50 (0.2.1.05): `src/cli/` deleted; the dispatcher collapses to the
`main:main` script entry which calls `uvicorn.run` directly. Any future
re-introduction of `from cli import ...` / `import cli` is forbidden
per AGENTS.md § Key Conventions § CLI (sunset directive). New operator
capabilities ship as Settings UI surfaces or `.env.example` slots.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.uses_sample_data_shims

_FORBIDDEN_PATTERNS = (
    re.compile(r"\bfrom\s+cli\s+import\b"),
    re.compile(r"\bfrom\s+cli\.\w+\s+import\b"),
    re.compile(r"^\s*import\s+cli\b", re.MULTILINE),
)


def test_no_cli_imports_in_src() -> None:
    src_root = Path(__file__).resolve().parent.parent / "src"
    assert src_root.is_dir(), f"expected src dir at {src_root}"

    offenders: list[tuple[Path, str]] = []
    for py_file in src_root.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        for pat in _FORBIDDEN_PATTERNS:
            m = pat.search(text)
            if m:
                offenders.append((py_file, m.group(0)))

    assert not offenders, (
        "Forbidden cli imports found (plan 50 / 0.2.1.05 deleted src/cli/):\n"
        + "\n".join(f"  {p.relative_to(src_root.parent)}: {hit!r}" for p, hit in offenders)
    )


def test_no_cli_directory_in_src() -> None:
    src_root = Path(__file__).resolve().parent.parent / "src"
    cli_dir = src_root / "cli"
    assert not cli_dir.exists(), (
        f"src/cli/ reappeared at {cli_dir}; plan 50 deleted it permanently. "
        f"New operator features go through the Settings UI or .env per "
        f"AGENTS.md § Key Conventions § CLI."
    )
