"""Naavik FastAPI entrypoint.

Plan 08 shrinks main.py to lifespan + middleware + router mounting + health.
Per-domain routers live under `src/ui/routes/`.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api import applications as api_applications
from api import auth as api_auth
from api import portfolio as api_portfolio
from api import profile as api_profile
from api import profile_answer as api_profile_answer
from api import scheduler as api_scheduler
from api import settings as api_settings
from config import settings as app_settings
from ui.routes import (
    auth,
    design,
    discover,
    email,
    fragments,
    integrations,
    jobs,
    outreach,
    overview,
    profile,
    setup_help,
    tracking,
)
from ui.routes import settings as ui_settings

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Boot the APScheduler with Wave-6 cron jobs registered.

    Scheduler is gracefully optional — if Postgres isn't reachable on boot
    (dev-only edge cases), the app still serves; jobs are no-ops.
    """
    if app_settings.debug:
        log.info("dev server up at http://localhost:8000 — visit /signup to create your account")

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
    # Plan 0.7.0.48 Wave 2 (2026-05-25): pass through `app_settings.debug` so
    # `request.app.debug` resolves correctly. Auth cookie code reads this attr
    # to decide `Secure=True/False`; when omitted, `request.app.debug` is always
    # False, so dev (http://localhost:8000) gets Secure cookies that the browser
    # refuses to send → infinite redirect to /login on every authed request.
    debug=app_settings.debug,
)

app.mount("/static", StaticFiles(directory="src/ui/static"), name="static")

app.include_router(auth.router)
app.include_router(api_auth.router)
app.include_router(api_profile.router)
app.include_router(api_profile_answer.router)
app.include_router(api_settings.router)
app.include_router(api_applications.router)
app.include_router(api_scheduler.router)
app.include_router(api_portfolio.router)
app.include_router(overview.router)
app.include_router(profile.router)
app.include_router(discover.router)
app.include_router(jobs.router)
app.include_router(tracking.router)
app.include_router(outreach.router)
app.include_router(ui_settings.router)
app.include_router(fragments.router)
app.include_router(integrations.router)
app.include_router(email.router)
app.include_router(design.router)
app.include_router(setup_help.router)


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("src/ui/static/favicon.svg", media_type="image/svg+xml")


def main():
    """`naavik` script entry — boots uvicorn against `main:app`.

    Plan 50 (0.2.1.05, 2026-05-20): `src/cli/` deleted. `python -m main`
    and `uvicorn src.main:app` are functionally identical to this entry.
    """
    import uvicorn

    from config import settings as app_settings

    uvicorn.run(
        "main:app",
        host=app_settings.host,
        port=app_settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
