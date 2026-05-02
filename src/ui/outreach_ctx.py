"""Project Application + Contact rows into Outreach UI dicts."""

from __future__ import annotations

from datetime import datetime

from db import sample_data as sd
from db.sample_data_models import Application, Contact
from models.enums import (
    AppEventKind,
    OutreachIntent,
    OutreachStatus,
    RecruiterState,
    ReferralState,
)

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


def _initial_color(s: str) -> tuple[str, str]:
    initial = (s or "?")[:1].upper()
    return initial, _COMPANY_COLORS.get(initial, "bg-slate-700")


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


def _engagement(a: Application, contact_count: int) -> str:
    if a.referral_state == ReferralState.PROVIDED:
        return "referred"
    if a.recruiter_state == RecruiterState.SILENT:
        return "no_reply_7d"
    if a.recruiter_state in {RecruiterState.RESPONDED, RecruiterState.ENGAGED}:
        return "awaiting_reply"
    if contact_count == 0:
        return "cold"
    return "active"


def _row_view(a: Application, contact_count: int) -> dict[str, object]:
    initial, color = _initial_color(a.company)
    return {
        "id": a.id,
        "company": a.company,
        "company_initial": initial,
        "company_color": color,
        "role": a.role,
        "team": a.team,
        "contacts_count": contact_count,
        "last_touch": _relative_label(a.updated_at),
        "status": a.status.value,
        "status_label": a.status.value.replace("_", " ").lower(),
        "outreach_engagement": _engagement(a, contact_count),
    }


def _contact_view(c: Contact, *, recent_outreach: list) -> dict[str, object]:
    initial, color = _initial_color(c.name)
    state = "cold"
    last_om = recent_outreach[0] if recent_outreach else None
    if last_om and last_om.status == OutreachStatus.REPLIED:
        # Did the contact provide a referral?
        state = (
            "referred_you"
            if last_om.intent == OutreachIntent.REFERRAL_REQUEST
            else "awaiting_reply"
        )
    elif last_om and last_om.status in {OutreachStatus.SENT, OutreachStatus.OPENED}:
        if (sd.TODAY - (last_om.sent_at or sd.TODAY)).days >= 7:
            state = "no_reply_7d"
        else:
            state = "awaiting_reply"
    last_activity = None
    if last_om and last_om.replied_at:
        last_activity = f"replied {_relative_label(last_om.replied_at)}"
    elif last_om and last_om.sent_at:
        last_activity = f"sent {_relative_label(last_om.sent_at)} · no reply"
    return {
        "display": {
            "name": c.name,
            "initial": initial,
            "color": color,
            "title": c.title or "",
            "team": None,
            "school": None,
            "mutuals_count": None,
            "degree": c.linkedin_degree,
            "last_activity": last_activity,
        },
        "state": state,
    }


async def build_outreach_ctx(*, selected_app_id: int | None = None) -> dict[str, object]:
    visible = await sd.applications_visible_in_tracking()
    followup = await sd.applications_in_followup_state()
    followup_ids = {a.id for a in followup}

    contact_counts: dict[int, int] = {}
    for a in visible:
        contact_counts[a.id] = len(await sd.contacts_for_application(a.id))

    followup_apps = [_row_view(a, contact_counts.get(a.id, 0)) for a in followup]
    active_apps = [
        _row_view(a, contact_counts.get(a.id, 0)) for a in visible if a.id not in followup_ids
    ]

    selected_app: Application | None = None
    if selected_app_id is not None:
        selected_app = await sd.get_application(selected_app_id)
    if selected_app is None and visible:
        selected_app = visible[0]

    detail = None
    contacts_view: list[dict[str, object]] = []
    recommended_move = None
    timeline_events: list[dict[str, object]] = []

    if selected_app is not None:
        initial, color = _initial_color(selected_app.company)
        detail = {
            "application_id": selected_app.id,
            "company": selected_app.company,
            "company_initial": initial,
            "company_color": color,
            "role": selected_app.role,
            "team": selected_app.team,
            "applied_label": _relative_label(selected_app.applied_at),
            "match_score": 0.86,
        }

        contacts = await sd.contacts_for_application(selected_app.id)
        for c in contacts:
            recent = await sd.outreach_messages_for_contact(c.id)
            contacts_view.append(_contact_view(c, recent_outreach=recent))

        # Recommended move — if any contact has a recent reply, suggest a follow-up;
        # else suggest the most-recent silent contact.
        primary = next((c for c in contacts), None)
        if primary:
            recommended_move = {
                "contact": {
                    "name": primary.name,
                    "title": primary.title or "Contact",
                    "company": primary.company,
                },
                "tone": "warm + direct",
                "last_touch": _relative_label(primary.last_touch_at),
                "context": "loop is open · keep momentum",
                "draft_body": (
                    f"Hey {primary.name.split()[0]} — wanted to follow up on the "
                    f"{selected_app.role} role. Anything I can do to keep the conversation "
                    "moving?"
                ),
            }

        events = await sd.app_events_for_application(selected_app.id)
        for e in events[:8]:
            kind_map = {
                AppEventKind.LINKEDIN_DM_SENT: "linkedin_dm",
                AppEventKind.LINKEDIN_DM_REPLIED: "linkedin_dm",
                AppEventKind.EMAIL_RECEIVED: "email",
                AppEventKind.EMAIL_SENT: "email",
                AppEventKind.REFERRAL_REQUESTED: "referral",
                AppEventKind.REFERRAL_PROVIDED: "referral",
                AppEventKind.INTERVIEW_SCHEDULED: "interview",
                AppEventKind.NOTE_ADDED: "note",
            }
            kind = kind_map.get(e.kind, "note")
            description = e.kind.value.replace("_", " ").capitalize()
            payload_preview = ""
            if e.kind == AppEventKind.EMAIL_RECEIVED:
                payload_preview = e.payload.get("subject_preview", "")
            elif e.kind == AppEventKind.NOTE_ADDED:
                payload_preview = e.payload.get("note_text_preview", "")
            timeline_events.append(
                {
                    "kind": kind,
                    "description": description,
                    "relative_time": _relative_label(e.occurred_at),
                    "payload_preview": payload_preview,
                }
            )

    referrals = sum(1 for a in visible if a.referral_state == ReferralState.PROVIDED)

    return {
        "active_count": len(visible),
        "followup_count": len(followup),
        "referrals_count": referrals,
        "followup_apps": followup_apps,
        "active_apps": active_apps,
        "selected_id": selected_app.id if selected_app else None,
        "detail": detail,
        "contacts": contacts_view,
        "recommended_move": recommended_move,
        "timeline_events": timeline_events,
    }
