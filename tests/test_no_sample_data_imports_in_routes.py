"""Regression lint: no `sample_data` imports in routes / ctx-builders.

Plan 60 / 0.2.7.17: `NAAVIK_PERSISTENCE` env-var removed; `src/db/sample_data.py`
stays but the only legitimate consumers are `src/db/seed.py` (production
seeding) + the pytest fixture suite. This walk catches any future regression
that reintroduces `from db import sample_data` (or kin) in a route or
ctx-builder module.

Allow-list:
  * `src/db/sample_data.py` itself
  * `src/db/sample_data_models.py` (canonical shadow types)
  * `src/db/seed.py` (production seeding consumer)
  * `src/models/__init__.py` (legacy import surface — currently empty
    re-export; kept allow-listed for forward compat)
  * Everything under `tests/` (test fixtures legitimately consume the shim)

Pattern mirrors `tests/test_no_vault_imports.py` + `tests/test_no_cli_imports.py`.
"""

from __future__ import annotations

import re
from pathlib import Path

_FORBIDDEN_PATTERNS = (
    re.compile(r"\bfrom\s+db\s+import\s+sample_data\b"),
    re.compile(r"\bfrom\s+db\.sample_data\s+import\b"),
    re.compile(r"\bfrom\s+db\.sample_data_models\s+import\b"),
    re.compile(r"^\s*import\s+db\.sample_data\b", re.MULTILINE),
)

# Files explicitly allowed to import sample_data (the production-seeding
# path + the shadow types module itself). Paths are relative to the repo root.
_ALLOW_LIST = {
    "src/db/sample_data.py",
    "src/db/sample_data_models.py",
    "src/db/seed.py",
    "src/models/__init__.py",
}


def test_no_sample_data_imports_in_routes_or_ctx():
    repo_root = Path(__file__).resolve().parent.parent
    src_root = repo_root / "src"
    assert src_root.is_dir(), f"expected src dir at {src_root}"

    # Walk the route + ctx-builder modules; the regression-lint scope is
    # narrower than the full repo (db/seed.py legitimately consumes the
    # shim). Plan 60 § Build sequence commit 3 says the walk targets
    # `src/ui/routes/` + `src/ui/*_ctx.py` + future `src/api/` routes.
    target_dirs = [
        src_root / "ui" / "routes",
        src_root / "api",
    ]
    target_files = [p for p in src_root.glob("ui/*_ctx.py") if p.is_file()]
    for d in target_dirs:
        if d.is_dir():
            target_files.extend(p for p in d.rglob("*.py") if p.is_file())

    offenders: list[tuple[Path, str]] = []
    for py_file in target_files:
        rel = py_file.relative_to(repo_root).as_posix()
        if rel in _ALLOW_LIST:
            continue
        text = py_file.read_text(encoding="utf-8")
        for pat in _FORBIDDEN_PATTERNS:
            m = pat.search(text)
            if m:
                offenders.append((py_file.relative_to(repo_root), m.group(0)))

    # Plan 69 (`0.3.3.12`, 2026-05-21) migrated the last 13 route + ctx
    # offenders off `db.sample_data` onto the service layer. The
    # `_KNOWN_LEGACY_OFFENDERS` allowlist is now empty + the lint
    # enforces zero `sample_data` imports anywhere in `src/ui/routes/`,
    # `src/ui/*_ctx.py`, or `src/api/`.
    assert not offenders, (
        "sample_data import detected in routes/ctx (plan 69 / 0.3.3.12 "
        "scoped this module to seed.py + tests). Migrate the new code to "
        "the service layer:\n" + "\n".join(f"  {p}: {hit!r}" for p, hit in offenders)
    )


def test_sample_data_module_still_exists():
    """Plan 60 keeps `src/db/sample_data.py` — only the env var is removed."""
    src_root = Path(__file__).resolve().parent.parent / "src"
    assert (src_root / "db" / "sample_data.py").exists()
