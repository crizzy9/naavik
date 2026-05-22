"""Regression lint: no vault imports anywhere in `src/`.

Plan 26 (0.2.0.01): `src/services/vault.py` deleted; every consumer
rewired to env vars. This 10-line walk catches a future regression that
reintroduces `from services import vault` / `import vault` somewhere.

Per `naavik-vault-sunset-guard`: the vault is gone. New secret-handling
code must go through `services/env_secrets.py` indicators + `.env`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.uses_sample_data_shims

_FORBIDDEN_PATTERNS = (
    # Match `from services import vault` or `from services.vault import ...`
    re.compile(r"\bfrom\s+services\s+import\s+vault\b"),
    re.compile(r"\bfrom\s+services\.vault\s+import\b"),
    # Match bare `import vault` (anchored — avoid matching `import vaultlike`
    # or `import vault_anything`).
    re.compile(r"^\s*import\s+vault\b", re.MULTILINE),
    # Catch the legacy alias usage.
    re.compile(r"\bvault_svc\b"),
)


def test_no_vault_imports_in_src():
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
        "Forbidden vault imports found (plan 26 / 0.2.0.01 deleted the vault):\n"
        + "\n".join(f"  {p.relative_to(src_root.parent)}: {hit!r}" for p, hit in offenders)
    )


def test_no_vault_module_file_in_src():
    src_root = Path(__file__).resolve().parent.parent / "src"
    vault_file = src_root / "services" / "vault.py"
    assert not vault_file.exists(), (
        f"src/services/vault.py reappeared at {vault_file}; plan 26 deleted it permanently."
    )


def test_no_vault_cli_files_in_src():
    src_root = Path(__file__).resolve().parent.parent / "src"
    for forbidden in (src_root / "cli" / "vault.py", src_root / "cli" / "init.py"):
        assert not forbidden.exists(), (
            f"{forbidden} reappeared; plan 26 deleted it along with the vault."
        )
