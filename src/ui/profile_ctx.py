"""Shape SAMPLE_DATA Profile/Experience/Bullet rows into the dicts the
profile components expect.

Lives in `ui/` (not `db/`) because the shape is presentation-bound; the DB
models stay free of these projections.
"""

from __future__ import annotations

from datetime import datetime

from db import sample_data as sd
from db.sample_data_models import (
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


def _format_dates(start: datetime, end: datetime | None) -> tuple[str, str]:
    """Return ("Jan 2017 — Present", "5y 2mo")."""
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    s = f"{months[start.month - 1]} {start.year}"
    if end is None:
        e = "Present"
        end_for_dur = sd.TODAY
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
        "tags": [t.value for t in b.tags],
        "selection_override": b.selection_override.value if b.selection_override else None,
    }


def app_questions_pairs(profile: Profile) -> list[tuple[str, str]]:
    """Return list of (label, display_value) tuples for the application-details section."""

    def _val(v):
        if v is None:
            return "—"
        if hasattr(v, "value"):
            return v.value.replace("_", " ")
        if isinstance(v, datetime):
            return v.strftime("%Y-%m-%d")
        return str(v).replace("_", " ")

    return [
        ("WORK AUTHORIZATION", _val(profile.work_authorization)),
        ("VISA SPONSORSHIP", _val(profile.visa_sponsorship_needed)),
        ("WILLING TO RELOCATE", _val(profile.willing_to_relocate)),
        (
            "NOTICE PERIOD",
            f"{profile.notice_period_days} days" if profile.notice_period_days else "—",
        ),
        (
            "SALARY EXPECTATION (USD)",
            f"${profile.salary_expectation_usd:,}" if profile.salary_expectation_usd else "—",
        ),
        ("EARLIEST START", _val(profile.earliest_start)),
        ("VETERAN STATUS", _val(profile.veteran_status)),
        ("DISABILITY STATUS", _val(profile.disability_status)),
        ("RACE / ETHNICITY", _val(profile.race_ethnicity)),
        ("GENDER IDENTITY", _val(profile.gender_identity)),
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
                "degree": e.degree,
                "institution": e.institution,
                "school": e.school,
                "location": e.location,
                "dates": dates,
                "gpa": e.gpa,
            }
        )
    return out


def project_dicts(projects: list[Project]) -> list[dict[str, object]]:
    return [
        {
            "title": p.title,
            "text": p.text,
            "tags": [t.value for t in p.tags],
            "link": p.link,
        }
        for p in projects
    ]


def skill_dicts(skills: list[Skill]) -> list[dict[str, object]]:
    return [{"category": s.category, "items": s.items} for s in skills]


def certification_dicts(certs: list[Certification]) -> list[dict[str, object]]:
    return [
        {
            "title": c.title,
            "issuer": c.issuer,
            "date": c.date.strftime("%Y-%m-%d") if c.date else None,
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
    {"id": "certifications", "label": "Certifications"},
]
