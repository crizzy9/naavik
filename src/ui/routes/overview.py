"""Overview route + supporting fragment + SSE endpoints."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from db.session import get_session
from models import User
from services import email_service, overview_service, profile_service
from services.auth import require_authed_session
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


def _effective_user_id(user: User | None) -> int:
    return user.id if user is not None else 1


def _greeting(now: datetime, full_name: str | None) -> str:
    h = now.hour
    if h < 12:
        base = "Good morning"
    elif h < 17:
        base = "Good afternoon"
    else:
        base = "Good evening"
    first = (full_name or "").strip().split(" ")[0]
    return f"{base}, {first}." if first else f"{base}."


def _date_pill(now: datetime) -> str:
    weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    tz = now.strftime("%Z") or "local"
    return (
        f"{weekdays[now.weekday()]} · {months[now.month - 1]} {now.day:>2} · "
        f"{now.hour:02d}:{now.minute:02d} {tz}"
    )


def _aware(when: datetime) -> datetime:
    return when if when.tzinfo is not None else when.replace(tzinfo=UTC)


def _relative_label(when: datetime) -> str:
    delta = datetime.now(UTC) - _aware(when)
    minutes = int(delta.total_seconds() // 60)
    if minutes < 60:
        return f"{max(minutes, 1)}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"


def _signal_view(thread):
    sender = "unknown"
    messages = thread.messages or []
    if messages:
        sender = messages[0].get("sender", "unknown") or "unknown"
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


async def _build_kpis(session: AsyncSession, user_id: int) -> list[dict[str, object]]:
    kpis = await overview_service.compute_kpis(session, user_id)
    return [
        {
            "label": "ACTIVE APPLICATIONS",
            "value": str(kpis.active_applications),
            "delta": None,
            "sub": "across 5 stages",
        },
        {
            "label": "RESPONSE RATE · 90D",
            "value": f"{kpis.response_rate * 100:.1f}%",
            "delta": None,
            "sub": None,
        },
        {
            "label": "ONSITE RATE",
            "value": f"{kpis.onsite_rate * 100:.1f}%",
            "delta": None,
            "sub": None,
        },
        {
            "label": "OFFER RATE",
            "value": f"{kpis.offer_rate * 100:.1f}%",
            "delta": None,
            "sub": f"{kpis.offer_count} offer{'s' if kpis.offer_count != 1 else ''}",
        },
    ]


# ─────────────────────────────────────────────────────────────────────────
# Page handler
# ─────────────────────────────────────────────────────────────────────────


@router.get("/", response_class=HTMLResponse, name="overview")
async def get_overview(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    user_id = _effective_user_id(user)
    now = datetime.now().astimezone()
    profile = await profile_service.get_profile(session, user_id)
    actions = await overview_service.compose_priority_actions(session, user_id)
    email_connected = bool(await email_service.list_accounts(session, user_id))
    threads = (
        await email_service.recent_signals(session, user_id, limit=6)
        if email_connected
        else []
    )
    counts = await overview_service.pipeline_strip_counts(session, user_id)
    return templates.TemplateResponse(
        request,
        "pages/overview.html",
        {
            "active_sidebar": "overview",
            "active_template_path": "/",
            "greeting": _greeting(now, profile.full_name if profile else None),
            "subline": (
                f"{len(actions)} priority actions queued for today"
                if actions
                else "No action items today."
            ),
            "date_pill": _date_pill(now),
            "kpis": await _build_kpis(session, user_id),
            "priority_actions": actions,
            "email_connected": email_connected,
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
async def fragment_priority_actions(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    user_id = _effective_user_id(user)
    actions = await overview_service.compose_priority_actions(session, user_id)
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
async def fragment_email_signal(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    user_id = _effective_user_id(user)
    threads = await email_service.recent_signals(session, user_id, limit=6)
    tmpl = templates.get_template("components/email_signal_row.html")
    out = [tmpl.render({"signal": _signal_view(t)}) for t in threads]
    return HTMLResponse("\n".join(out))


@router.get(
    "/_fragments/overview/pipeline-strip",
    response_class=HTMLResponse,
    name="overview_pipeline_fragment",
)
async def fragment_pipeline_strip(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    user_id = _effective_user_id(user)
    counts = await overview_service.pipeline_strip_counts(session, user_id)
    return templates.TemplateResponse(
        request,
        "components/pipeline_strip.html",
        {"counts": counts},
    )


# ─────────────────────────────────────────────────────────────────────────
# SSE — email-signal stream (consumed by Overview + Tracking)
# ─────────────────────────────────────────────────────────────────────────


@router.get("/api/v1/tracking/email-signals", name="tracking_email_signals_sse")
async def get_email_signals_stream(
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_authed_session),
):
    """SSE — emits an email-signal-row partial periodically.

    Gated on a real EmailAccount: with no inbox connected there is nothing
    to stream, so return 204 instead of an empty 200 stream (P6.1 — the
    Overview template also skips sse-connect entirely when unconfigured).
    """
    user_id = _effective_user_id(user)
    if not await email_service.list_accounts(session, user_id):
        return Response(status_code=204)

    threads = await email_service.recent_signals(session, user_id, limit=10)

    async def gen():
        tmpl = templates.get_template("components/email_signal_row.html")
        for t in threads:
            html = tmpl.render({"signal": _signal_view(t)})
            yield f"event: signal\ndata: {html.replace(chr(10), ' ')}\n\n"
            await asyncio.sleep(0.6)

    return StreamingResponse(gen(), media_type="text/event-stream")
