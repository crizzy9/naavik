"""Shared Jinja2Templates instance + global registrations.

Every UI router imports `templates` from here so:
- `templates.env.globals` registrations (STATUS_DOT_COLORS, TAG_VOCAB, etc.) are
  visible everywhere
- A single template directory is configured once
"""

from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="src/ui/templates")

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
templates.env.globals["TAG_VOCAB"] = TAG_VOCAB
