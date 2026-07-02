"""Plan 09a · Issue 4 — human-readable labels for application-question enums.

Each label list mirrors the canonical enum in `src/models/enums.py` 1:1.
Templates render dropdowns from these tuples; the read-only Profile view
calls `app_q_label(field, value)` to display the human-friendly label.

Wording follows job-application convention (e.g., "Will you require visa
sponsorship?") rather than abstract enum names ("h1b") — per the user's
2026-05-02 plan-09a Q3 answer.

Schema: each map = `[(enum_value, human_label), ...]` plus a `dict` lookup
for read-only display. Adding new options later is a one-line edit + the
matching enum addition in `models/enums.py`.
"""

from __future__ import annotations

# Each list is the option set for a `<select>`; first item = "no answer" sentinel.
# An empty `value` lets the read-only view fall back to "—" when nothing's set.

WORK_AUTH_OPTIONS: list[tuple[str, str]] = [
    ("", "—"),
    ("us_citizen", "US Citizen"),
    ("green_card", "Permanent Resident (Green Card)"),
    ("h1b", "H-1B Visa Holder"),
    ("opt_cpt", "OPT / CPT (F-1 Student)"),
    ("other_requires_sponsorship", "Other — Requires Sponsorship"),
]

VISA_SPONSORSHIP_OPTIONS: list[tuple[str, str]] = [
    ("", "—"),
    ("not_needed", "No — sponsorship not needed"),
    ("needed_now", "Yes — Now"),
    ("needed_future", "Yes — In the Future"),
]

RELOCATE_OPTIONS: list[tuple[str, str]] = [
    ("", "—"),
    ("open", "Yes — Open to relocate"),
    ("open_to_list", "Open to specific cities"),
    ("remote_only", "Remote only"),
    ("no", "No — Not willing to relocate"),
]

VETERAN_OPTIONS: list[tuple[str, str]] = [
    ("", "—"),
    ("not_veteran", "Not a veteran"),
    ("veteran", "Veteran"),
    ("prefer_not_to_say", "Prefer not to say"),
]

DISABILITY_OPTIONS: list[tuple[str, str]] = [
    ("", "—"),
    ("no", "No"),
    ("yes", "Yes"),
    ("prefer_not_to_say", "Prefer not to say"),
]

RACE_OPTIONS: list[tuple[str, str]] = [
    ("", "—"),
    ("asian", "Asian"),
    ("black", "Black or African American"),
    ("hispanic", "Hispanic or Latino"),
    ("native_american", "Native American or Alaska Native"),
    ("pacific_islander", "Native Hawaiian or Pacific Islander"),
    ("white", "White"),
    ("two_or_more", "Two or more races"),
    ("prefer_not_to_say", "Prefer not to say"),
]

GENDER_OPTIONS: list[tuple[str, str]] = [
    ("", "—"),
    ("male", "Male"),
    ("female", "Female"),
    ("non_binary", "Non-binary"),
    ("prefer_not_to_say", "Prefer not to say"),
]

# Field name → option list. Keys match Profile model attribute names exactly,
# so callers can do `APP_Q_OPTIONS[field_name]` directly.
APP_Q_OPTIONS: dict[str, list[tuple[str, str]]] = {
    "work_authorization": WORK_AUTH_OPTIONS,
    "visa_sponsorship_needed": VISA_SPONSORSHIP_OPTIONS,
    "willing_to_relocate": RELOCATE_OPTIONS,
    "veteran_status": VETERAN_OPTIONS,
    "disability_status": DISABILITY_OPTIONS,
    "race_ethnicity": RACE_OPTIONS,
    "gender_identity": GENDER_OPTIONS,
}

# Pre-computed value→label maps for read-only display.
APP_Q_LABEL_MAPS: dict[str, dict[str, str]] = {
    field: dict(options) for field, options in APP_Q_OPTIONS.items()
}


def app_q_label(field: str, value: str | None) -> str:
    """Return the human-readable label for an enum value (or '—' if unset)."""
    if not value:
        return "—"
    return APP_Q_LABEL_MAPS.get(field, {}).get(str(value), str(value))


# ── Job-description formatter (item 2, 2026-07) ─────────────────────────
# Scraped JDs arrive as plain-text blobs; rendering them with
# `whitespace-pre-line` read like a wall of text. This formats the blob
# into real structure — section headings, bullet lists, paragraphs — with
# every piece of input HTML-escaped first (no raw HTML injection; scraped
# markup renders inert as text).

import re
from html import escape as _html_escape

from markupsafe import Markup

_JD_BULLET_RE = re.compile(r"^\s*(?:[-–—*•·◦▪‣]|\d{1,2}[.)])\s+(.*)$")
# Known JD section names — matched case-insensitively when a short line is
# made of them (with optional trailing colon).
_JD_SECTION_WORDS = (
    "about",
    "responsibilities",
    "requirements",
    "qualifications",
    "benefits",
    "perks",
    "compensation",
    "what you'll do",
    "what you will do",
    "what you'll bring",
    "who you are",
    "nice to have",
    "nice-to-have",
    "bonus points",
    "the role",
    "the team",
    "your impact",
    "why join",
    "our stack",
    "tech stack",
    "interview process",
    "equal opportunity",
)


def _jd_is_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > 64 or stripped.endswith((".", ",", ";")):
        return False
    if stripped.endswith(":"):
        return True
    letters = [c for c in stripped if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) > 0.85 and len(letters) >= 4:
        return True  # ALL-CAPS section banner
    lowered = stripped.lower().rstrip(":")
    return any(lowered.startswith(w) for w in _JD_SECTION_WORDS) and len(stripped.split()) <= 6


def format_jd(text: str | None) -> Markup:
    """Plain-text JD → structured, fully-escaped HTML."""
    if not text:
        return Markup("")
    out: list[str] = []
    para: list[str] = []
    in_list = False

    def _close_para() -> None:
        nonlocal para
        if para:
            body = "<br>".join(_html_escape(line) for line in para)
            out.append(f'<p class="text-sm text-slate-300 leading-relaxed">{body}</p>')
            para = []

    def _close_list() -> None:
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            _close_para()
            _close_list()
            continue
        m = _JD_BULLET_RE.match(line)
        if m:
            _close_para()
            if not in_list:
                out.append('<ul class="list-disc pl-5 flex flex-col gap-1 marker:text-slate-500">')
                in_list = True
            out.append(
                f'<li class="text-sm text-slate-300 leading-relaxed">{_html_escape(m.group(1))}</li>'
            )
            continue
        if _jd_is_heading(line):
            _close_para()
            _close_list()
            heading = _html_escape(line.strip().rstrip(":"))
            out.append(
                '<h4 class="text-[11px] uppercase tracking-wide text-slate-400 '
                f'font-mono font-medium mt-4 first:mt-0 mb-1">{heading}</h4>'
            )
            continue
        _close_list()
        para.append(line.strip())
    _close_para()
    _close_list()
    return Markup("\n".join(out))
