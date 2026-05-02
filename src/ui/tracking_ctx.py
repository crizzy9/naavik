"""Project Application rows into tracking_card / tracking_list_row dicts."""

from __future__ import annotations

from datetime import datetime

from db import sample_data as sd
from db.sample_data_models import Application
from models.enums import ApplicationStatus, RecruiterState, ReferralState

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


def _initial_color(company: str) -> tuple[str, str]:
    initial = (company or "?")[:1].upper()
    return initial, _COMPANY_COLORS.get(initial, "bg-slate-700")


def _salary_range(a: Application) -> str | None:
    if a.salary_min and a.salary_max:
        return f"${a.salary_min // 1000}-{a.salary_max // 1000}k"
    if a.salary_min:
        return f"${a.salary_min // 1000}k+"
    return None


def _relative_label(when: datetime | None) -> str:
    if when is None:
        return "—"
    delta = sd.TODAY - when
    days = delta.days
    if days < 1:
        return "today"
    if days == 1:
        return "1d ago"
    if days < 30:
        return f"{days}d ago"
    return f"{days // 30}mo ago"


def _context_chip(a: Application) -> tuple[str | None, str]:
    """Return (chip_label, tone) — small status pill rendered on tracking_card."""
    if a.referral_state == ReferralState.PROVIDED:
        return ("referral", "emerald")
    if a.referral_state in {ReferralState.REQUESTED, ReferralState.IN_FLIGHT}:
        return ("referral pending", "amber")
    if a.recruiter_state == RecruiterState.SILENT:
        return ("reply pending", "amber")
    return (None, "slate")


def application_to_card(a: Application) -> dict[str, object]:
    initial, color = _initial_color(a.company)
    chip, tone = _context_chip(a)
    return {
        "id": a.id,
        "company": a.company,
        "company_initial": initial,
        "company_color": color,
        "role": a.role,
        "team": a.team,
        "score": int(a.salary_max and 80) if False else 80,  # placeholder; jobs carry score
        "salary_range": _salary_range(a),
        "status": a.status.value,
        "status_label": a.status.value.replace("_", " ").lower(),
        "context_chip": chip,
        "context_chip_tone": tone,
        "sub_state_pills": [],
    }


def application_to_list_row(a: Application) -> dict[str, object]:
    initial, color = _initial_color(a.company)
    return {
        "id": a.id,
        "company": a.company,
        "company_initial": initial,
        "company_color": color,
        "role": a.role,
        "team": a.team,
        "status": a.status.value,
        "status_label": a.status.value.replace("_", " "),
        "score": None,
        "salary_range": _salary_range(a),
        "last_activity": _relative_label(a.updated_at),
        "source": (a.board.value if a.board else "manual"),
    }


def _columns_for_board(apps: list[Application], *, show_closed: bool) -> list[dict[str, object]]:
    visible = [
        ApplicationStatus.APPLIED,
        ApplicationStatus.RECRUITER_SCREEN,
        ApplicationStatus.ONSITE_LOOP,
        ApplicationStatus.OFFER,
    ]
    if show_closed:
        visible.append(ApplicationStatus.CLOSED)
    out = []
    for status in visible:
        cards = [application_to_card(a) for a in apps if a.status == status]
        out.append({"status": status.value, "cards": cards})
    return out


async def build_tracking_ctx(
    *, view: str = "board", show_closed: bool = False
) -> dict[str, object]:
    visible_apps = await sd.applications_visible_in_tracking()
    all_apps = visible_apps + await sd.closed_applications() if show_closed else visible_apps
    closed = await sd.closed_applications()
    columns = _columns_for_board(all_apps, show_closed=show_closed)

    followup = await sd.applications_in_followup_state()
    items = []
    for a in followup[:4]:
        contacts = await sd.contacts_for_application(a.id)
        c = contacts[0] if contacts else None
        items.append(
            {
                "contact": {
                    "name": c.name if c else "Recruiter",
                    "initial": (c.name[:1].upper() if c else a.company[:1].upper()),
                    "color": _initial_color(c.company if c else a.company)[1],
                },
                "application": {"company": a.company},
                "last_touch_label": (
                    f"sent {_relative_label(a.updated_at)} · no reply"
                    if a.recruiter_state == RecruiterState.SILENT
                    else f"asked you back {_relative_label(a.updated_at)}"
                ),
                "action_label": "Draft reply",
                "action_url": f"/outreach?application={a.id}",
            }
        )

    integrations = [
        {
            "name": "Gmail",
            "icon": "mail",
            "state": "connected",
            "account": "[email protected]",
            "connect_url": "/api/v1/integrations/gmail/connect",
            "disconnect_url": "/api/v1/integrations/gmail/disconnect",
            "description": None,
        },
        {
            "name": "Outlook",
            "icon": "mail",
            "state": "not_connected",
            "account": None,
            "connect_url": "/api/v1/integrations/outlook/connect",
            "disconnect_url": None,
            "description": None,
        },
        {
            "name": "Calendar",
            "icon": "calendar",
            "state": "not_connected",
            "account": None,
            "connect_url": "/api/v1/integrations/calendar/connect",
            "disconnect_url": None,
            "description": "auto-create events",
        },
    ]

    return {
        "current_view": view,
        "show_closed": show_closed,
        "columns": columns,
        "rows": [application_to_list_row(a) for a in visible_apps],
        "active_count": len(visible_apps),
        "closed_count": len(closed),
        "followup_count": len(followup),
        "followup_items": items,
        "integrations": integrations,
    }
