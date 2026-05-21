"""Regression lint — `src/services/scorer.py` must not return.

Plan 65 § T11 split the flat `src/services/scorer.py` into a
`src/services/scorer/` package. Backward-compat is provided via
`__init__.py` re-exports, so callsites that imported
`from services.scorer import apply_visa_filter` continue to work.

If someone reintroduces the flat file (via revert, merge, or a
"refactor"), this test trips. Keep the package.
"""

from __future__ import annotations

from pathlib import Path


def test_no_flat_scorer_module():
    repo_root = Path(__file__).resolve().parent.parent
    flat = repo_root / "src" / "services" / "scorer.py"
    assert not flat.exists(), (
        "src/services/scorer.py reappeared — plan 65 split it into "
        "src/services/scorer/ package. Re-import the modules via "
        "the __init__.py re-exports."
    )

    pkg = repo_root / "src" / "services" / "scorer"
    assert pkg.is_dir(), "src/services/scorer/ package missing"
    assert (pkg / "__init__.py").exists(), (
        "src/services/scorer/__init__.py missing — re-exports are the backward-compat surface"
    )
    assert (pkg / "visa.py").exists(), "src/services/scorer/visa.py missing"
