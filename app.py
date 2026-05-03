"""Repo-root re-export so `fastapi dev` (no path arg) finds the app.

The canonical entrypoint is `src/main:app`. Plan 10a (PC.2, 2026-05-02)
added this two-line shim so contributors don't have to memorize the path.
"""

from src.main import app

__all__ = ["app"]
