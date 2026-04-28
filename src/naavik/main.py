from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from naavik.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="Naavik",
    description="Your intelligent career navigator",
    version="0.1.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="src/naavik/ui/static"), name="static")

templates = Jinja2Templates(directory="src/naavik/ui/templates")


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {"title": "Dashboard"},
    )


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}


def main():
    uvicorn.run(
        "naavik.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
