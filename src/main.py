"""Naavik FastAPI entrypoint.

Plan 08 shrinks main.py to lifespan + middleware + router mounting + health.
Per-domain routers live under `src/ui/routes/`.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from api import applications as api_applications
from api import auth as api_auth
from api import portfolio as api_portfolio
from api import profile as api_profile
from api import settings as api_settings
from config import settings as app_settings
from ui.routes import (
    auth,
    design,
    discover,
    email,
    fragments,
    integrations,
    outreach,
    overview,
    profile,
    tracking,
)
from ui.routes import settings as ui_settings

log = logging.getLogger(__name__)


_DEV_CREDENTIALS_ECHO_DELAY_SEC = 0.75


async def _echo_dev_credentials_after_start() -> None:
    """Re-emit `<data_dir>/dev-credentials` near the bottom of startup logs.

    Plan 10c (10c.3a, 2026-05-11): with `PC_DISABLE_TUI=true` in the
    orchestrator, all four `[deps]`/`[migrate]`/`[seed]`/`[app]` streams
    interleave; the `[seed]` credential line lands ~5 s before uvicorn's
    "Application startup complete." and scrolls above the fold. The
    on-disk file at `<data_dir>/dev-credentials` (written by `db/seed.py`
    when debug + SELF_HOSTED + generated) is the canonical recovery path
    via `cat`; this echo also surfaces it through the FastAPI logger so
    it interleaves with `[app]` lines after the uvicorn banner.

    Best-effort. If the file doesn't exist (env-supplied password, debug
    off, cloud-tier deploy, or a re-seed that found an existing user),
    this is a no-op.
    """
    try:
        await asyncio.sleep(_DEV_CREDENTIALS_ECHO_DELAY_SEC)
        creds_path = Path(app_settings.data_dir) / "dev-credentials"
        if not creds_path.exists():
            return
        log.info("─── dev credentials (also at ~/.naavik/dev-credentials) ───")
        for line in creds_path.read_text().splitlines():
            if line.strip():
                log.info("  %s", line)
        log.info("───────────────────────────────────────────────────────────")
    except Exception as exc:  # noqa: BLE001
        # Never let credential echo crash the lifespan. The file is the
        # canonical recovery path either way.
        log.debug("dev-credentials echo skipped: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Wave 6: boot the APScheduler with Wave-6 cron jobs registered.

    Scheduler is gracefully optional — if Postgres isn't reachable on boot
    (dev-only edge cases), the app still serves; jobs are no-ops.

    Plan 10c (10c.3a, 2026-05-11): in debug mode, also spawn a fire-and-
    forget task that re-emits the seeded dev credential ~750 ms after
    startup so it lands at the bottom of the orchestrator's interleaved
    scrollback (see `_echo_dev_credentials_after_start`).
    """
    if app_settings.debug:
        asyncio.create_task(_echo_dev_credentials_after_start())

    try:
        from scheduler import shutdown as shutdown_scheduler
        from scheduler import start as start_scheduler
    except ImportError:
        start_scheduler = shutdown_scheduler = None

    if start_scheduler is not None:
        try:
            await start_scheduler()
        except Exception as exc:  # noqa: BLE001
            log.warning("scheduler boot failed: %s", exc)
    try:
        yield
    finally:
        if shutdown_scheduler is not None:
            try:
                await shutdown_scheduler()
            except Exception as exc:  # noqa: BLE001
                log.warning("scheduler shutdown errored: %s", exc)


app = FastAPI(
    title="Naavik",
    description="Self-hosted-first career automation platform",
    version="0.1.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="src/ui/static"), name="static")

app.include_router(auth.router)
app.include_router(api_auth.router)
app.include_router(api_profile.router)
app.include_router(api_settings.router)
app.include_router(api_applications.router)
app.include_router(api_portfolio.router)
app.include_router(overview.router)
app.include_router(profile.router)
app.include_router(discover.router)
app.include_router(tracking.router)
app.include_router(outreach.router)
app.include_router(ui_settings.router)
app.include_router(fragments.router)
app.include_router(integrations.router)
app.include_router(email.router)
app.include_router(design.router)


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}


def main():
    """Back-compat alias for `python -m main`.

    Plan 10b (item 5, 2026-05-03) moved the canonical CLI dispatch to
    `cli.main:main`. The actual `naavik` script entry point now resolves
    there. This shim exists so anyone running `python -m main` (or
    importing `main.main`) keeps booting the server.
    """
    from cli.main import cmd_serve

    return cmd_serve()


if __name__ == "__main__":
    main()
