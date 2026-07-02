"""Project Profile/Experience/Bullet rows into the dicts the profile
components expect.

Lives in `ui/` (not `db/`) because the shape is presentation-bound; the DB
models stay free of these projections.
"""

from __future__ import annotations

from datetime import UTC, datetime

from models import (
    Bullet,
    Certification,
    Education,
    Experience,
    Profile,
    Project,
    Skill,
)

_INITIAL_COLORS = {
    "S": "bg-indigo-600",
    "P": "bg-emerald-600",
    "C": "bg-amber-600",
    "N": "bg-rose-600",
}


def _company_initial_color(company: str) -> tuple[str, str]:
    initial = (company or "?")[:1].upper()
    return initial, _INITIAL_COLORS.get(initial, "bg-slate-700")


def _tag_values(tags) -> list[str]:
    """Normalize `tags` across shadow `list[Tag]` enum + real `list[str]`."""
    return [t.value if hasattr(t, "value") else str(t) for t in (tags or [])]


def _format_dates(start: datetime, end: datetime | None) -> tuple[str, str]:
    """Return ("Jan 2017 — Present", "5y 2mo")."""
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    s = f"{months[start.month - 1]} {start.year}"
    if end is None:
        e = "Present"
        end_for_dur = datetime.now(UTC)
    else:
        e = f"{months[end.month - 1]} {end.year}"
        end_for_dur = end
    months_total = (end_for_dur.year - start.year) * 12 + (end_for_dur.month - start.month)
    years = months_total // 12
    rem_months = months_total % 12
    if years and rem_months:
        dur = f"{years}y {rem_months}mo"
    elif years:
        dur = f"{years}y"
    else:
        dur = f"{rem_months}mo"
    return f"{s} — {e}", dur


def hero_dict(profile: Profile) -> dict[str, object]:
    """Build the `profile_hero` dict (initials, contact_chips, visa label)."""
    name = profile.full_name
    initials = "".join([p[:1].upper() for p in name.split()][:2]) or "?"
    contacts: list[dict[str, object]] = []
    if profile.email:
        contacts.append({"kind": "mail", "value": profile.email, "href": f"mailto:{profile.email}"})
    if profile.phone:
        contacts.append({"kind": "phone", "value": profile.phone, "href": None})
    if profile.github_handle:
        contacts.append(
            {
                "kind": "github",
                "value": "/" + profile.github_handle,
                "href": f"https://github.com/{profile.github_handle}",
            }
        )
    if profile.linkedin_handle:
        contacts.append(
            {
                "kind": "linkedin",
                "value": "/in/" + profile.linkedin_handle,
                "href": f"https://linkedin.com/in/{profile.linkedin_handle}",
            }
        )
    if profile.portfolio_url:
        contacts.append(
            {
                "kind": "portfolio",
                "value": profile.portfolio_url.replace("https://", ""),
                "href": profile.portfolio_url,
            }
        )

    visa_label: str | None = None
    if profile.work_authorization and profile.work_authorization.value == "h1b":
        visa_label = "H1B · Requires sponsorship"

    return {
        "name": name,
        "initials": initials,
        "title": profile.headline,
        "company": profile.current_company,
        "location": profile.location,
        "open_to_opportunities": profile.open_to_opportunities,
        "visa_label": visa_label,
        "contacts": contacts,
        "summary_short": profile.summary_short,
        "summary_full": profile.summary_full,
    }


# Plan 73 (0.3.2.03) — sparkline strip data projection.
#
# Family labels rendered in the hero strip. Source-of-truth is the
# `Profile.score_history.families[*].family` string written by the cron.
_FAMILY_LABEL = {
    "ai-ml": "ML",
    "genai": "GenAI",
    "frontend": "Frontend",
    "backend": "Backend",
    "data-eng": "Data eng",
    "devops": "DevOps",
    "platform": "Platform",
    "leadership": "Leadership",
    "product": "Product",
    "other": "Other",
}


def _sparkline_color(score_current: float) -> str:
    """Score-threshold color band per DESIGN.md (emerald/indigo/amber/rose)."""
    if score_current >= 0.80:
        return "emerald"
    if score_current >= 0.60:
        return "indigo"
    if score_current >= 0.40:
        return "amber"
    return "rose"


def _sparkline_polyline_points(daily_means: list[float | None]) -> str:
    """Compute SVG polyline `points` attr for `daily_means`.

    Domain: viewBox 0..100 (width) × 0..24 (height). x = index / (N-1) * 100;
    y = (1 - score) * 24 (so 1.0 sits at the top, 0.0 at the bottom). Missing
    days carry forward the last known value; a leading run of None is
    rendered as a flat baseline at the first known value.
    """
    if not daily_means:
        return ""
    n = len(daily_means)
    non_null = [m for m in daily_means if m is not None]
    if not non_null:
        return ""
    fallback = non_null[0]
    last_known = fallback
    points: list[str] = []
    for i, m in enumerate(daily_means):
        if m is None:
            y_val = last_known
        else:
            y_val = m
            last_known = m
        x = (i / (n - 1) * 100) if n > 1 else 50
        y = (1 - max(0.0, min(1.0, y_val))) * 24
        points.append(f"{x:.1f},{y:.1f}")
    return " ".join(points)


def score_trend_strip(
    score_history: dict | None,
    *,
    top_k: int = 3,
) -> dict[str, object]:
    """Project `Profile.score_history` into a template-friendly dict.

    Returns:
        {
            "has_data": bool,
            "rows": [
                {
                    "family": "ai-ml",
                    "label": "ML",
                    "scored_count_30d": 23,
                    "score_current": 0.84,
                    "score_delta_30d": 0.12,
                    "color": "emerald",
                    "polyline_points": "0.0,12.2 3.4,11.9 ...",
                    "delta_sign": "up",  # "up" | "down" | "flat"
                    "delta_abs": 0.12,
                },
                ...
            ]
        }
    """
    if not score_history or not score_history.get("families"):
        return {"has_data": False, "rows": []}

    families = sorted(
        score_history["families"],
        key=lambda f: f.get("scored_count_30d", 0),
        reverse=True,
    )[:top_k]

    rows: list[dict[str, object]] = []
    for f in families:
        family = f.get("family", "other")
        current = float(f.get("score_current", 0.0) or 0.0)
        delta = float(f.get("score_delta_30d", 0.0) or 0.0)
        daily_means = f.get("daily_means") or []
        delta_sign = "up" if delta > 0.005 else ("down" if delta < -0.005 else "flat")
        rows.append(
            {
                "family": family,
                "label": _FAMILY_LABEL.get(family, family),
                "scored_count_30d": int(f.get("scored_count_30d", 0)),
                "score_current": current,
                "score_delta_30d": delta,
                "delta_abs": abs(delta),
                "delta_sign": delta_sign,
                "color": _sparkline_color(current),
                "polyline_points": _sparkline_polyline_points(daily_means),
            }
        )
    return {"has_data": bool(rows), "rows": rows}


def experience_dict(exp: Experience) -> dict[str, object]:
    initial, color = _company_initial_color(exp.company)
    dates, duration = _format_dates(exp.start_date, exp.end_date)
    return {
        "company": exp.company,
        "team": exp.team,
        "title": exp.title,
        "location": exp.location,
        "dates": dates,
        "duration": duration,
        "initial": initial,
        "color": color,
    }


def bullet_dict(b: Bullet) -> dict[str, object]:
    return {
        "id": b.id,
        "text": b.text,
        "tags": _tag_values(b.tags),
        "selection_override": b.selection_override.value if b.selection_override else None,
    }


def app_questions_pairs(profile: Profile) -> list[tuple[str, str]]:
    """Return list of (label, display_value) tuples for the application-details section.

    Plan 09a · Issue 4 — labels follow real job-application phrasing; values use
    the human-readable map from `ui.template_helpers.app_q_label` instead of raw
    enum strings (e.g., "h1b" → "H-1B Visa Holder").
    """
    from ui.template_helpers import app_q_label

    def _enum_value(v) -> str | None:
        if v is None:
            return None
        return v.value if hasattr(v, "value") else str(v)

    def _date(v):
        if v is None:
            return "—"
        if isinstance(v, datetime):
            return v.strftime("%Y-%m-%d")
        return str(v)

    return [
        (
            "ARE YOU AUTHORIZED TO WORK IN THE US?",
            app_q_label("work_authorization", _enum_value(profile.work_authorization)),
        ),
        (
            "WILL YOU REQUIRE VISA SPONSORSHIP?",
            app_q_label("visa_sponsorship_needed", _enum_value(profile.visa_sponsorship_needed)),
        ),
        (
            "ARE YOU OPEN TO RELOCATING?",
            app_q_label("willing_to_relocate", _enum_value(profile.willing_to_relocate)),
        ),
        (
            "NOTICE PERIOD",
            f"{profile.notice_period_days} days" if profile.notice_period_days else "—",
        ),
        (
            "SALARY EXPECTATION (USD)",
            f"${profile.salary_expectation_usd:,}" if profile.salary_expectation_usd else "—",
        ),
        ("EARLIEST START", _date(profile.earliest_start)),
        (
            "ARE YOU A VETERAN?",
            app_q_label("veteran_status", _enum_value(profile.veteran_status)),
        ),
        (
            "DO YOU HAVE A DISABILITY?",
            app_q_label("disability_status", _enum_value(profile.disability_status)),
        ),
        (
            "RACE / ETHNICITY (FOR EEO REPORTING)",
            app_q_label("race_ethnicity", _enum_value(profile.race_ethnicity)),
        ),
        ("GENDER", app_q_label("gender_identity", _enum_value(profile.gender_identity))),
    ]


def application_readiness(profile: Profile) -> dict[str, object]:
    """Drives the right-rail Application Readiness card."""
    fields = [
        {
            "name": "work_authorization",
            "label": "Work authorization",
            "value": profile.work_authorization.value if profile.work_authorization else None,
        },
        {
            "name": "visa_sponsorship_needed",
            "label": "Visa sponsorship needed",
            "value": profile.visa_sponsorship_needed.value
            if profile.visa_sponsorship_needed
            else None,
        },
        {
            "name": "veteran_status",
            "label": "Veteran status",
            "value": profile.veteran_status.value if profile.veteran_status else None,
        },
        {
            "name": "disability_status",
            "label": "Disability status",
            "value": profile.disability_status.value if profile.disability_status else None,
        },
        {
            "name": "race_ethnicity",
            "label": "Race / ethnicity (EEO)",
            "value": profile.race_ethnicity.value if profile.race_ethnicity else None,
        },
        {
            "name": "gender_identity",
            "label": "Gender",
            "value": profile.gender_identity.value if profile.gender_identity else None,
        },
    ]
    out = []
    missing = 0
    for f in fields:
        filled = bool(f["value"])
        if not filled:
            missing += 1
        out.append(
            {**f, "filled": filled, "value": (f["value"].replace("_", " ") if f["value"] else None)}
        )
    return {"missing_count": missing, "fields": out}


def education_dicts(educations: list[Education]) -> list[dict[str, object]]:
    out = []
    for e in educations:
        dates, _ = _format_dates(e.start_date, e.end_date)
        out.append(
            {
                "id": e.id,
                "degree": e.degree,
                "institution": e.institution,
                "school": e.school,
                "location": e.location,
                "dates": dates,
                "start_value": e.start_date.strftime("%Y-%m-%d") if e.start_date else "",
                "end_value": e.end_date.strftime("%Y-%m-%d") if e.end_date else "",
                "gpa": e.gpa,
            }
        )
    return out


def project_dicts(projects: list[Project]) -> list[dict[str, object]]:
    return [
        {
            "id": p.id,
            "kind": getattr(p, "kind", "project"),
            "title": p.title,
            "text": p.text,
            "tags": _tag_values(p.tags),
            "tags_csv": ", ".join(_tag_values(p.tags)),
            "link": p.link,
            "date_value": p.date.strftime("%Y-%m-%d") if p.date else "",
        }
        for p in projects
    ]


def skill_dicts(skills: list[Skill]) -> list[dict[str, object]]:
    return [
        {
            "id": s.id,
            "category": s.category,
            "items": s.items,
            "items_csv": ", ".join(s.items or []),
        }
        for s in skills
    ]


def certification_dicts(certs: list[Certification]) -> list[dict[str, object]]:
    return [
        {
            "id": c.id,
            "title": c.title,
            "issuer": c.issuer,
            "date": c.date.strftime("%Y-%m-%d") if c.date else None,
            "date_value": c.date.strftime("%Y-%m-%d") if c.date else "",
            "description": c.description,
        }
        for c in certs
    ]


PROFILE_ANCHORS = [
    {"id": "summary", "label": "Summary"},
    {"id": "experience", "label": "Experience"},
    {"id": "application-details", "label": "Application details"},
    {"id": "skills", "label": "Skills"},
    {"id": "education", "label": "Education"},
    {"id": "projects", "label": "Projects"},
    {"id": "open-source", "label": "Open source"},
    {"id": "certifications", "label": "Certifications"},
]
