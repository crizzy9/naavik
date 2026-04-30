from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import settings


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

templates = Jinja2Templates(directory="src/ui/templates")


def _placeholder(request: Request, *, screen: str, route: str, section: str):
    return templates.TemplateResponse(
        request,
        "placeholder.html",
        {"screen": screen, "route": route, "section": section},
    )


@app.get("/", response_class=HTMLResponse)
async def overview(request: Request):
    return _placeholder(request, screen="Overview", route="/", section="3")


@app.get("/login", response_class=HTMLResponse)
async def login(request: Request):
    return _placeholder(request, screen="Login", route="/login", section="1")


@app.get("/onboarding", response_class=HTMLResponse)
async def onboarding(request: Request):
    return _placeholder(
        request,
        screen="Onboarding · resume upload",
        route="/onboarding",
        section="2",
    )


@app.get("/profile", response_class=HTMLResponse)
async def profile(request: Request):
    return _placeholder(request, screen="Profile", route="/profile", section="4")


@app.get("/profile/edit", response_class=HTMLResponse)
async def profile_edit(request: Request):
    return _placeholder(
        request,
        screen="Profile editor",
        route="/profile/edit",
        section="5",
    )


@app.get("/discover", response_class=HTMLResponse)
async def discover(request: Request):
    return _placeholder(request, screen="Discover", route="/discover", section="7")


@app.get("/discover/{job_id}", response_class=HTMLResponse)
async def discover_review(request: Request, job_id: str):
    return _placeholder(
        request,
        screen="Discover · review & apply",
        route=f"/discover/{job_id}",
        section="8",
    )


@app.get("/tracking", response_class=HTMLResponse)
async def tracking(request: Request):
    return _placeholder(request, screen="Tracking", route="/tracking", section="9")


@app.get("/outreach", response_class=HTMLResponse)
async def outreach(request: Request):
    return _placeholder(request, screen="Outreach", route="/outreach", section="10")


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    return _placeholder(request, screen="Settings", route="/settings", section="11")


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
