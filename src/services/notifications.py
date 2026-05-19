"""Notifications — Discord webhook + Telegram outbound + in-app toast.

Per BACKEND.md § L.3, § L.4, § H.1 + plan 10 § C.5.

Wave 6 ships outbound. Telegram inbound + Discord moderation are Phase 5.
Plan 26 (0.2.0.01): credentials moved from the encrypted vault to env vars
(`DISCORD_WEBHOOK_URL`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`) consumed
by pydantic-settings in `src/config.py`. Per-event toggles still live in
`Settings.notifications_enabled` (JSON dict).
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

from config import settings as app_settings
from models import Application, Job, Settings

log = logging.getLogger(__name__)

# Per-event toggle keys (matching Settings.notifications_enabled JSON shape).
EVENT_NEW_HIGH_SCORE = "new_high_score_job"
EVENT_APPLICATION_SENT = "application_sent"
EVENT_INTERVIEW_SCHEDULED = "interview_scheduled"
EVENT_OFFER_RECEIVED = "offer_received"
EVENT_REJECTION = "rejection"
EVENT_AUTO_APPLY_FAILED = "auto_apply_failed"


# ── Toast / SSE in-app routing ─────────────────────────────────────────


@dataclass(slots=True)
class Toast:
    kind: str  # info / success / warning / error
    title: str
    body: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


# Process-wide queue. SSE handler at /_fragments/toast subscribes.
_TOAST_QUEUE: asyncio.Queue[Toast] = asyncio.Queue(maxsize=128)


async def push_toast(kind: str, title: str, body: str | None = None) -> None:
    try:
        _TOAST_QUEUE.put_nowait(Toast(kind=kind, title=title, body=body))
    except asyncio.QueueFull:
        log.warning("toast queue full; dropping notification %r", title)


async def stream_toasts() -> AsyncIterator[str]:
    """SSE generator — yields a chunk per toast.

    Caller wires this to /_fragments/toast (consumed by #toast-region OOB swap).
    """
    while True:
        toast = await _TOAST_QUEUE.get()
        payload = {
            "kind": toast.kind,
            "title": toast.title,
            "body": toast.body or "",
            "ts": toast.timestamp.isoformat(),
        }
        yield f"event: toast\ndata: {json.dumps(payload)}\n\n"


# ── Discord webhook ────────────────────────────────────────────────────


def _discord_url() -> str | None:
    return app_settings.discord_webhook_url or None


def _embed_for_event(
    event: str,
    *,
    application: Application | None = None,
    job: Job | None = None,
) -> dict[str, Any]:
    if event == EVENT_NEW_HIGH_SCORE and job is not None:
        return {
            "title": f"New high-score job: {job.role} @ {job.company}",
            "description": (job.description or "")[:280],
            "url": job.url,
            "color": 5793266,  # cyan-ish
            "fields": [
                {"name": "Score", "value": f"{job.score:.2f}", "inline": True},
                {
                    "name": "Location",
                    "value": job.location or "Remote",
                    "inline": True,
                },
            ],
            "footer": {"text": "naavik · scraped just now"},
        }
    if event == EVENT_APPLICATION_SENT and application is not None:
        return {
            "title": f"Application submitted: {application.role} @ {application.company}",
            "color": 5763719,  # green
            "fields": [
                {
                    "name": "Board",
                    "value": (application.board.value if application.board else "manual"),
                    "inline": True,
                }
            ],
        }
    if event == EVENT_INTERVIEW_SCHEDULED and application is not None:
        return {
            "title": f"Interview scheduled: {application.company}",
            "color": 16744192,
        }
    if event == EVENT_OFFER_RECEIVED and application is not None:
        return {
            "title": f"OFFER · {application.company} · {application.role}",
            "color": 16766720,
        }
    if event == EVENT_REJECTION and application is not None:
        return {
            "title": f"Rejection · {application.company} · {application.role}",
            "color": 13632027,
        }
    if event == EVENT_AUTO_APPLY_FAILED and application is not None:
        return {
            "title": f"Auto-apply failed · {application.company}",
            "description": (application.submission_artifacts or {})
            .get("last_failure", {})
            .get("message", ""),
            "color": 13632027,
        }
    return {"title": event, "color": 9807270}


def _is_event_enabled(settings: Settings, event: str) -> bool:
    payload = settings.notifications_enabled or {}
    if not payload:
        # Defaults: rejections off, everything else on.
        defaults = {
            EVENT_NEW_HIGH_SCORE: True,
            EVENT_APPLICATION_SENT: True,
            EVENT_INTERVIEW_SCHEDULED: True,
            EVENT_OFFER_RECEIVED: True,
            EVENT_REJECTION: False,
            EVENT_AUTO_APPLY_FAILED: True,
        }
        return defaults.get(event, True)
    return bool(payload.get(event, True))


async def send_discord(
    *,
    settings: Settings,
    event: str,
    application: Application | None = None,
    job: Job | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> bool:
    """Post a rich embed to Discord. Returns True on success.

    Silently no-ops if no webhook configured or the event is muted.
    """
    if not _is_event_enabled(settings, event):
        return False
    url = _discord_url()
    if not url:
        return False
    embed = _embed_for_event(event, application=application, job=job)
    body = {"embeds": [embed]}
    client = http_client or httpx.AsyncClient(timeout=10.0)
    owns = http_client is None
    try:
        resp = await client.post(url, json=body)
        if resp.status_code >= 300:
            log.warning("discord webhook failed: %d %s", resp.status_code, resp.text[:200])
            return False
        return True
    except httpx.RequestError as exc:
        log.warning("discord webhook errored: %s", exc)
        return False
    finally:
        if owns:
            await client.aclose()


# ── Telegram outbound ──────────────────────────────────────────────────


def _telegram_token() -> str | None:
    return app_settings.telegram_bot_token or None


def _telegram_chat_id() -> str | None:
    return app_settings.telegram_chat_id or None


def _telegram_text_for_event(
    event: str,
    *,
    application: Application | None = None,
    job: Job | None = None,
) -> str:
    if event == EVENT_NEW_HIGH_SCORE and job is not None:
        return (
            f"📌 New match: *{job.role}* @ *{job.company}*\n"
            f"Score: `{job.score:.2f}` · {job.location or 'Remote'}\n"
            f"{job.url}"
        )
    if event == EVENT_APPLICATION_SENT and application is not None:
        return (
            f"📤 Submitted: *{application.role}* @ *{application.company}* "
            f"({application.board.value if application.board else 'manual'})"
        )
    if event == EVENT_INTERVIEW_SCHEDULED and application is not None:
        return f"🗓️ Interview · {application.company}"
    if event == EVENT_OFFER_RECEIVED and application is not None:
        return f"🎉 OFFER · {application.company} · {application.role}"
    if event == EVENT_REJECTION and application is not None:
        return f"🚪 Rejection · {application.company} · {application.role}"
    if event == EVENT_AUTO_APPLY_FAILED and application is not None:
        return (
            f"⚠️ Auto-apply failed · {application.company}\n"
            f"{(application.submission_artifacts or {}).get('last_failure', {}).get('message', '')}"
        )
    return event


async def send_telegram(
    *,
    settings: Settings,
    event: str,
    application: Application | None = None,
    job: Job | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> bool:
    if not _is_event_enabled(settings, event):
        return False
    token = _telegram_token()
    chat = _telegram_chat_id()
    if not token or not chat:
        return False
    text = _telegram_text_for_event(event, application=application, job=job)
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = {"chat_id": chat, "text": text, "parse_mode": "Markdown"}
    client = http_client or httpx.AsyncClient(timeout=10.0)
    owns = http_client is None
    try:
        resp = await client.post(url, json=body)
        if resp.status_code >= 300:
            log.warning("telegram failed: %d %s", resp.status_code, resp.text[:200])
            return False
        return True
    except httpx.RequestError as exc:
        log.warning("telegram errored: %s", exc)
        return False
    finally:
        if owns:
            await client.aclose()


# ── Composite event emitters (called from services) ───────────────────


async def notify_new_high_score(
    *, settings: Settings, job: Job, http_client: httpx.AsyncClient | None = None
) -> None:
    if job.score < settings.notify_threshold:
        return
    await asyncio.gather(
        send_discord(
            settings=settings, event=EVENT_NEW_HIGH_SCORE, job=job, http_client=http_client
        ),
        send_telegram(
            settings=settings, event=EVENT_NEW_HIGH_SCORE, job=job, http_client=http_client
        ),
        push_toast("info", "New match", f"{job.role} @ {job.company} (score {job.score:.2f})"),
        return_exceptions=True,
    )


async def notify_application_submitted(
    *,
    settings: Settings,
    application: Application,
    http_client: httpx.AsyncClient | None = None,
) -> None:
    await asyncio.gather(
        send_discord(
            settings=settings,
            event=EVENT_APPLICATION_SENT,
            application=application,
            http_client=http_client,
        ),
        send_telegram(
            settings=settings,
            event=EVENT_APPLICATION_SENT,
            application=application,
            http_client=http_client,
        ),
        push_toast(
            "success",
            "Application submitted",
            f"{application.role} @ {application.company}",
        ),
        return_exceptions=True,
    )


async def notify_auto_apply_failed(
    *,
    settings: Settings,
    application: Application,
    http_client: httpx.AsyncClient | None = None,
) -> None:
    await asyncio.gather(
        send_discord(
            settings=settings,
            event=EVENT_AUTO_APPLY_FAILED,
            application=application,
            http_client=http_client,
        ),
        send_telegram(
            settings=settings,
            event=EVENT_AUTO_APPLY_FAILED,
            application=application,
            http_client=http_client,
        ),
        push_toast(
            "warning",
            "Auto-apply needs attention",
            f"{application.company} · check Discover stuck queue",
        ),
        return_exceptions=True,
    )


async def notify_admin_error(
    *, settings: Settings, message: str, http_client: httpx.AsyncClient | None = None
) -> None:
    """Critical admin error — only fires if `Settings.notify_on_errors=True`."""
    if not settings.notify_on_errors:
        return
    url = _discord_url()
    if not url:
        return
    body = {"content": f"⚠️ Naavik admin error: {message[:1000]}"}
    client = http_client or httpx.AsyncClient(timeout=10.0)
    owns = http_client is None
    try:
        await client.post(url, json=body)
    except httpx.RequestError:
        pass
    finally:
        if owns:
            await client.aclose()
