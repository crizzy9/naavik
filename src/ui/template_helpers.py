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
