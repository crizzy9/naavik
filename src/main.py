"""Naavik FastAPI entrypoint.

Plan 08 shrinks main.py to lifespan + middleware + router mounting + health.
Per-domain routers live under `src/ui/routes/`.
"""

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from api import applications as api_applications
from api import auth as api_auth
from api import portfolio as api_portfolio
from api import profile as api_profile
from api import settings as api_settings
from config import settings
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Wave 6: boot the APScheduler with Wave-6 cron jobs registered.

    Scheduler is gracefully optional — if Postgres isn't reachable on boot
    (dev-only edge cases), the app still serves; jobs are no-ops.
    """
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
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
