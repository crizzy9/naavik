"""`main:main` script-entry smoke test — plan 50 § Item 2 risk-table fold-in.

Plan 50 (0.2.1.05) collapsed `cli.main:main` into `main:main`. The old
`tests/test_cli.py` exercised argparse dispatch + bare-invocation
routing; both are obsolete now. This file pins the one remaining
behavioral assertion: invoking `main()` calls `uvicorn.run` with the
expected app reference.
"""

from __future__ import annotations

import os

# Bypass SECRET_KEY validator so `from main import main` (transitively imports
# config) doesn't ValidationError at collection time.
os.environ.setdefault("NAAVIK_DEBUG", "1")


def test_main_invokes_uvicorn(monkeypatch) -> None:
    """Calling `main:main()` runs `uvicorn.run("main:app", host=..., port=...)`."""
    import uvicorn

    called: dict[str, object] = {}

    def _fake_run(app_ref: str, **kwargs):
        called["app_ref"] = app_ref
        called["kwargs"] = kwargs

    monkeypatch.setattr(uvicorn, "run", _fake_run)

    from main import main

    main()

    assert called.get("app_ref") == "main:app"
    kwargs = called.get("kwargs") or {}
    assert "host" in kwargs
    assert "port" in kwargs
    assert kwargs.get("reload") is False
