"""Overview route + supporting fragment + SSE endpoints."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from db import sample_data as sd
from models.enums import ApplicationStatus
from ui.templates_setup import templates

router = APIRouter()


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


def _greeting(now: datetime) -> str:
    h = now.hour
    if h < 12:
        return "Good morning, Shyam."
    if h < 17:
        return "Good afternoon, Shyam."
    return "Good evening, Shyam."


def _date_pill(now: datetime) -> str:
    weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return (
        f"{weekdays[now.weekday()]} · {months[now.month - 1]} {now.day:>2} · "
        f"{now.hour:02d}:{now.minute:02d} PT"
    )


def _signal_view(thread):
    sender = "unknown"
    if thread.messages:
        sender = thread.messages[0].get("sender", "unknown") or "unknown"
    initial = sender[:1].upper() if sender else "?"
    return {
        "sender": sender,
        "sender_initial": initial,
        "sender_color": _COMPANY_COLORS.get(initial, "bg-slate-700"),
        "subject": thread.subject,
        "classification": thread.classification.value.upper(),
        "classification_label": thread.classification.value.replace("_", " "),
        "score": None,
        "relative_time": _relative_label(thread.latest_message_at),
    }


def _relative_label(when: datetime) -> str:
    delta = sd.TODAY - when
    minutes = int(delta.total_seconds() // 60)
    if minutes < 60:
        return f"{max(minutes, 1)}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"


async def _build_kpis() -> list[dict[str, object]]:
    active = await sd.kpi_active_applications()
    rr90 = await sd.kpi_response_rate_90d()
    or90 = await sd.kpi_onsite_rate_90d()
    of90 = await sd.kpi_offer_rate_90d()
    offer_apps = await sd.applications_by_status(ApplicationStatus.OFFER)
    return [
        {
            "label": "ACTIVE APPLICATIONS",
            "value": str(active),
            "delta": None,
            "sub": "across 5 stages",
        },
        {
            "label": "RESPONSE RATE · 90D",
            "value": f"{rr90 * 100:.1f}%",
            "delta": "+2.1%",
            "sub": "3× market avg",
        },
        {
            "label": "ONSITE RATE",
            "value": f"{or90 * 100:.1f}%",
            "delta": "-0.4%",
            "sub": None,
        },
        {
            "label": "OFFER RATE",
            "value": f"{of90 * 100:.1f}%",
            "delta": "+0.7%",
            "sub": f"{len(offer_apps)} offer{'s' if len(offer_apps) != 1 else ''} · 1 pending",
        },
    ]


# ─────────────────────────────────────────────────────────────────────────
# Page handler
# ─────────────────────────────────────────────────────────────────────────


@router.get("/", response_class=HTMLResponse, name="overview")
async def get_overview(request: Request):
    now = datetime.now(UTC)
    actions = await sd.priority_actions()
    threads = await sd.email_signal_feed(limit=6)
    counts = await sd.pipeline_strip_counts()
    return templates.TemplateResponse(
        request,
        "pages/overview.html",
        {
            "active_sidebar": "overview",
            "active_template_path": "/",
            "greeting": _greeting(now),
            "subline": (
                f"{len(actions)} priority actions queued for today"
                if actions
                else "No action items today."
            ),
            "date_pill": _date_pill(now),
            "kpis": await _build_kpis(),
            "priority_actions": actions,
            "email_signals": [_signal_view(t) for t in threads],
            "pipeline_counts": counts,
            "active_count": sum(counts.values()) - counts.get("CLOSED", 0),
        },
    )


# ─────────────────────────────────────────────────────────────────────────
# Fragment endpoints
# ─────────────────────────────────────────────────────────────────────────


@router.get(
    "/_fragments/overview/priority-actions",
    response_class=HTMLResponse,
    name="overview_priority_actions_fragment",
)
async def fragment_priority_actions(request: Request):
    actions = await sd.priority_actions()
    tmpl = templates.get_template("components/priority_action_row.html")
    out = []
    for i, a in enumerate(actions, start=1):
        out.append(tmpl.render({**a, "index": i}))
    return HTMLResponse("\n".join(out))


@router.get(
    "/_fragments/overview/email-signal",
    response_class=HTMLResponse,
    name="overview_email_signal_fragment",
)
async def fragment_email_signal(request: Request):
    threads = await sd.email_signal_feed(limit=6)
    tmpl = templates.get_template("components/email_signal_row.html")
    out = [tmpl.render({"signal": _signal_view(t)}) for t in threads]
    return HTMLResponse("\n".join(out))


@router.get(
    "/_fragments/overview/pipeline-strip",
    response_class=HTMLResponse,
    name="overview_pipeline_fragment",
)
async def fragment_pipeline_strip(request: Request):
    counts = await sd.pipeline_strip_counts()
    return templates.TemplateResponse(
        request,
        "components/pipeline_strip.html",
        {"counts": counts},
    )


# ─────────────────────────────────────────────────────────────────────────
# SSE — email-signal stream (consumed by Overview + Tracking)
# ─────────────────────────────────────────────────────────────────────────


@router.get("/api/v1/tracking/email-signals", name="tracking_email_signals_sse")
async def get_email_signals_stream():
    """SSE — emits an email-signal-row partial periodically. Loops through
    the seeded EmailThreads.
    """

    async def gen():
        threads = await sd.email_signal_feed(limit=10)
        tmpl = templates.get_template("components/email_signal_row.html")
        for t in threads:
            html = tmpl.render({"signal": _signal_view(t)})
            # Collapse newlines so SSE framing is intact.
            yield f"event: signal\ndata: {html.replace(chr(10), ' ')}\n\n"
            await asyncio.sleep(0.6)

    return StreamingResponse(gen(), media_type="text/event-stream")
