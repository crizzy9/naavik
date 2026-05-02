"""Naavik FastAPI entrypoint.

Plan 08 shrinks main.py to lifespan + middleware + router mounting + health.
Per-domain routers live under `src/ui/routes/`.
"""

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="Naavik",
    description="Self-hosted-first career automation platform",
    version="0.1.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="src/ui/static"), name="static")

app.include_router(auth.router)
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
