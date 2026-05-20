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

    # Phase 1 transitional reality: many existing route + ctx files still
    # import sample_data. Plan 60 commit 1 + 2 set the service-layer
    # foundation; follow-up plan 0.2.7.17a moves the rewires. Until those
    # land, mark the existing offenders as known-acceptable; the test
    # PRINCIPLE is enforced for NEW files only.
    #
    # When a future plan moves a route file off sample_data, remove its
    # entry from this list. When the list is empty, this fixture-only
    # guarantee fully holds.
    _KNOWN_LEGACY_OFFENDERS = {
        "src/ui/routes/discover.py",
        "src/ui/routes/email.py",
        "src/ui/routes/fragments.py",
        "src/ui/routes/outreach.py",
        "src/ui/routes/overview.py",
        "src/ui/routes/profile.py",
        "src/ui/routes/settings.py",
        "src/ui/routes/tracking.py",
        "src/ui/discover_ctx.py",
        "src/ui/discover_review_ctx.py",
        "src/ui/outreach_ctx.py",
        "src/ui/profile_ctx.py",
        "src/ui/tracking_ctx.py",
    }
    new_offenders = [
        (p, hit) for p, hit in offenders if p.as_posix() not in _KNOWN_LEGACY_OFFENDERS
    ]

    assert not new_offenders, (
        "New sample_data import detected in routes/ctx (plan 60 / 0.2.7.17 "
        "scoped this module to seed.py + tests). Migrate the new code to "
        "the service layer:\n" + "\n".join(f"  {p}: {hit!r}" for p, hit in new_offenders)
    )


def test_sample_data_module_still_exists():
    """Plan 60 keeps `src/db/sample_data.py` — only the env var is removed."""
    src_root = Path(__file__).resolve().parent.parent / "src"
    assert (src_root / "db" / "sample_data.py").exists()
