"""Regression lint: no `db.seed` imports anywhere in `src/` or `tests/`.

Plan 83 (0.7.0.36): `src/db/seed.py` deleted; first-time setup now uses
`/signup`. This walk catches a future regression that reintroduces
`from db.seed import seed` / `import db.seed` somewhere.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.uses_sample_data_shims

_FORBIDDEN_PATTERNS = (
    re.compile(r"\bfrom\s+db\s+import\s+seed\b"),
    re.compile(r"\bfrom\s+db\.seed\s+import\b"),
    re.compile(r"^\s*import\s+db\.seed\b", re.MULTILINE),
)


def test_no_db_seed_imports_in_src():
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
        "Forbidden db.seed imports found (plan 83 / 0.7.0.36 deleted seed.py):\n"
        + "\n".join(f"  {p.relative_to(src_root.parent)}: {hit!r}" for p, hit in offenders)
    )


def test_no_db_seed_module_file_in_src():
    src_root = Path(__file__).resolve().parent.parent / "src"
    seed_file = src_root / "db" / "seed.py"
    assert not seed_file.exists(), (
        f"src/db/seed.py reappeared at {seed_file}; plan 83 deleted it permanently."
    )
