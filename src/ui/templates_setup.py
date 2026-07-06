"""Shared Jinja2Templates instance + global registrations.

Every UI router imports `templates` from here so:
- `templates.env.globals` registrations (STATUS_DOT_COLORS, TAG_VOCAB, etc.) are
  visible everywhere
- Starlette `context_processors` (csrf_token, ...) inject per-request values
  into every TemplateResponse(request, name, ctx) render — covers all
  callsites without per-handler edits. Plan 45 (0.2.0.11d).
- A single template directory is configured once
"""

from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from services.auth import CSRF_COOKIE
from ui.template_helpers import APP_Q_LABEL_MAPS, APP_Q_OPTIONS, app_q_label, format_jd


def _csrf_token_ctx(request: Request) -> dict[str, str]:
    """Inject the `naavik_csrf` cookie value into every template context.

    Empty string when the cookie is absent keeps `validate_csrf`'s
    empty-rejects-empty invariant for unauthenticated landing pages.
    Issuing a fresh token here would break the double-submit pairing
    (cookie set by `_set_session_cookies` would not match the rendered
    header). Sync per Starlette's documented constraint;
    `request.cookies` is a sync property.
    """
    return {"csrf_token": request.cookies.get(CSRF_COOKIE, "")}


templates = Jinja2Templates(
    directory="src/ui/templates",
    context_processors=[_csrf_token_ctx],
)


def _static_asset_version() -> str:
    """Cache-buster for `/static/*` URLs in base.html.

    `<package version>.<max mtime of the static files>`, computed once per
    process. Starlette's StaticFiles sends no Cache-Control, so browsers
    heuristically cache JS/CSS — after a code change, users got new HTML
    against STALE base.js/styles.css (the dead-collapse-button regression).
    Dev: any static edit restarts the reloader → new mtime → new URL.
    Nix builds: store mtimes are constant, so the package version carries
    the bust across releases.
    """
    from importlib.metadata import PackageNotFoundError, version
    from pathlib import Path

    try:
        pkg_version = version("naavik")
    except PackageNotFoundError:  # pragma: no cover — always installed via uv
        pkg_version = "0"
    static_dir = Path(__file__).parent / "static"
    try:
        mtime = max(
            int(p.stat().st_mtime) for p in static_dir.iterdir() if p.suffix in {".js", ".css"}
        )
    except (ValueError, OSError):  # pragma: no cover — static dir always present
        mtime = 0
    return f"{pkg_version}.{mtime}"


# Status pipeline color map per DESIGN.md § Status Pipeline.
# 6 keys: DRAFT (pre-submission, hidden in Tracking) + 5 visible stages.
STATUS_DOT_COLORS: dict[str, str] = {
    "DRAFT": "bg-slate-500",
    "APPLIED": "bg-indigo-500",
    "RECRUITER_SCREEN": "bg-cyan-500",
    "ONSITE_LOOP": "bg-amber-500",
    "OFFER": "bg-emerald-500",
    "CLOSED": "bg-rose-500",
    # Auxiliary tones reused by status_dot.html for non-pipeline indicators.
    "info": "bg-sky-500",
    "warning": "bg-amber-500",
    "success": "bg-emerald-500",
    "danger": "bg-rose-500",
}

# Fixed 9-tag vocabulary per DESIGN.md § Components > Tag / Chip > Tag vocabulary.
TAG_VOCAB: list[str] = [
    "ai-ml",
    "backend",
    "frontend",
    "devops",
    "data-eng",
    "genai",
    "leadership",
    "platform",
    "product",
]

templates.env.globals["STATUS_DOT_COLORS"] = STATUS_DOT_COLORS
templates.env.globals["static_v"] = _static_asset_version()
templates.env.globals["TAG_VOCAB"] = TAG_VOCAB
# Plan 09a · Issue 4 — application-question dropdown options + value→label maps.
templates.env.globals["APP_Q_OPTIONS"] = APP_Q_OPTIONS
templates.env.globals["APP_Q_LABEL_MAPS"] = APP_Q_LABEL_MAPS
templates.env.globals["app_q_label"] = app_q_label
# Item 2 (2026-07) — plain-text JD → structured escaped HTML.
templates.env.filters["format_jd"] = format_jd
