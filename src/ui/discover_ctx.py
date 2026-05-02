"""Project Job + Application rows into Discover swipe-card / up-next dicts."""

from __future__ import annotations

from datetime import datetime

from db import sample_data as sd
from db.sample_data_models import Job

_COMPANY_COLORS = {
    "F": "bg-fuchsia-700",
    "A": "bg-emerald-700",
    "S": "bg-indigo-700",
    "L": "bg-purple-700",
    "N": "bg-rose-700",
    "P": "bg-amber-700",
    "R": "bg-amber-700",
    "D": "bg-indigo-700",
    "M": "bg-cyan-700",
    "C": "bg-amber-700",
    "T": "bg-sky-700",
    "G": "bg-rose-600",
    "O": "bg-emerald-700",
}

_GRADIENTS = {
    "S": ("from-indigo-600", "to-purple-600"),
    "A": ("from-emerald-600", "to-cyan-600"),
    "L": ("from-fuchsia-600", "to-indigo-600"),
    "F": ("from-amber-600", "to-rose-600"),
    "M": ("from-cyan-600", "to-indigo-600"),
    "R": ("from-emerald-600", "to-indigo-600"),
    "D": ("from-indigo-600", "to-purple-600"),
    "N": ("from-rose-600", "to-purple-600"),
    "P": ("from-amber-600", "to-emerald-600"),
    "O": ("from-emerald-600", "to-indigo-600"),
}


def _initial_color(s: str) -> tuple[str, str]:
    initial = (s or "?")[:1].upper()
    return initial, _COMPANY_COLORS.get(initial, "bg-slate-700")


def _gradient(initial: str) -> tuple[str, str]:
    return _GRADIENTS.get(initial, ("from-indigo-600", "to-purple-600"))


def _salary_range(j: Job) -> str | None:
    if j.salary_min and j.salary_max:
        equity = f" + {j.equity_pct}%" if j.equity_pct else ""
        return f"${j.salary_min // 1000}-{j.salary_max // 1000}k{equity}"
    return None


def _relative_label(when: datetime | None) -> str:
    if when is None:
        return "—"
    delta = sd.TODAY - when
    minutes = int(delta.total_seconds() // 60)
    if minutes < 60:
        return f"{max(minutes, 1)}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    return f"{hours // 24}d ago"


def _jd_bullets(j: Job) -> list[str]:
    if j.criteria:
        return j.criteria[:5]
    return [f"Top role at {j.company}", "Strong fit for your background"]


def swipe_card_dict(j: Job, *, warm_intro_label: str | None = None) -> dict[str, object]:
    initial, color = _initial_color(j.company)
    grad_from, grad_to = _gradient(initial)
    location, work_mode = (j.location, None)
    if j.location and " · " in j.location:
        location, work_mode = j.location.split(" · ", 1)
    return {
        "id": j.id,
        "company": j.company,
        "company_initial": initial,
        "company_color": color,
        "gradient_from": grad_from,
        "gradient_to": grad_to,
        "role": j.role,
        "team": j.team,
        "score": int(round(j.score * 100)),
        "location": location,
        "salary_range": _salary_range(j),
        "work_mode": work_mode,
        "posted_relative": _relative_label(j.posted_at or j.found_at),
        "jd_bullets": _jd_bullets(j),
        "warm_intro_label": warm_intro_label,
        "tags": [t.value for t in j.tags],
        "match_breakdown": j.match_breakdown,
        "match_overall": j.score,
        "visa_friendly": j.visa_restrictions == "sponsorship_available",
    }


def up_next_dict(j: Job) -> dict[str, object]:
    initial, color = _initial_color(j.company)
    return {
        "id": j.id,
        "company": j.company,
        "company_initial": initial,
        "company_color": color,
        "role": j.role,
        "salary_range": _salary_range(j),
        "score": int(round(j.score * 100)),
    }


def stats_strip(today_apps: int) -> dict[str, int]:
    return {
        "applied": today_apps,
        "auto": 1,
        "manual": 0,
        "saved": 0,
        "skipped": 0,
        "scanned": 142,
    }


async def build_discover_ctx() -> dict[str, object]:
    queue = await sd.discover_queue()
    saved = await sd.saved_jobs()
    drafts = await sd.auto_apply_queue()
    stuck = await sd.stuck_drafts()

    current = queue[0] if queue else None
    warm_label = None
    if current and current.warm_intro_contact_id:
        c = await sd.get_contact(current.warm_intro_contact_id)
        warm_label = c.name.split()[0] if c else None

    up_next = [up_next_dict(j) for j in queue[1:5]]

    stuck_views = []
    for app in stuck:
        if not app.job_id:
            continue
        job = await sd.get_job(app.job_id)
        if not job:
            continue
        v = up_next_dict(job)
        v["state"] = "stuck"
        v["last_failure"] = (app.submission_artifacts or {}).get("last_failure")
        stuck_views.append(v)

    return {
        "current_card": (
            swipe_card_dict(current, warm_intro_label=warm_label) if current else None
        ),
        "up_next": up_next,
        "stuck_drafts": stuck_views,
        "saved_count": len(saved),
        "auto_apply_drafts": [
            up_next_dict(await sd.get_job(d.job_id))
            for d in drafts
            if d.job_id and await sd.get_job(d.job_id) is not None
        ]
        if drafts
        else [],
        "stats": stats_strip(today_apps=2),
        "unswiped_count": len(queue),
    }
