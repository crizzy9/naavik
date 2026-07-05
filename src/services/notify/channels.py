"""Channel transports — Discord webhook + Telegram bot senders.

Split out of services/notifications.py in plan 91 Phase 4.6;
behaviour unchanged. Internal calls to patched seams route through
`svc()` (the facade) so test interception keeps working.
"""

from __future__ import annotations

import logging

import httpx

from config import settings as app_settings
from models import Application, Job, JobScrapeRun, Settings
from services.notify.events import (
    EVENT_SCRAPE_RUN_NEW_JOBS,
    _embed_for_event,
    _embed_for_scrape_run,
    _is_event_enabled,
    _telegram_text_for_event,
    _telegram_text_for_scrape_run,
)

log = logging.getLogger(__name__)


def svc():
    """The `services.notifications` facade, resolved at call time — keeps
    `patch("services.notifications.X")` seams intercepting internal calls
    (plan 91 Phase 4.6)."""
    from services import notifications

    return notifications


# ── Test message (Settings · Notifications "Test" button) ───────────────


async def send_test_message(
    *,
    channel: str,
    http_client: httpx.AsyncClient | None = None,
) -> bool:
    """Send a real "test" message to `channel` ("discord" | "telegram").

    Returns True on a 2xx from the provider. Unlike the event emitters this
    ignores per-event toggles (a manual test button should always fire) and
    talks to the provider directly. Callers pre-check env presence and render
    the outcome.
    """
    text = "✅ Naavik test notification — your channel is wired up correctly."
    client = http_client or httpx.AsyncClient(timeout=10.0)
    owns = http_client is None
    try:
        if channel == "discord":
            url = svc()._discord_url()
            if not url:
                return False
            resp = await client.post(url, json={"content": text})
        elif channel == "telegram":
            token = svc()._telegram_token()
            chat = svc()._telegram_chat_id()
            if not token or not chat:
                return False
            resp = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": text},
            )
        else:
            return False
        if resp.status_code >= 300:
            log.warning("%s test message failed: %d %s", channel, resp.status_code, resp.text[:200])
            return False
        return True
    except httpx.RequestError as exc:
        log.warning("%s test message errored: %s", channel, exc)
        return False
    finally:
        if owns:
            await client.aclose()


# ── Discord webhook ────────────────────────────────────────────────────


def _discord_url() -> str | None:
    return app_settings.discord_webhook_url or None


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
    url = svc()._discord_url()
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
    token = svc()._telegram_token()
    chat = svc()._telegram_chat_id()
    if not token or not chat:
        return False
    text = _telegram_text_for_event(event, application=application, job=job)
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    # No parse_mode (plan 46 / 0.2.0.12a): scraper-controlled role/company
    # would otherwise allow Markdown injection. Telegram auto-linkifies URLs
    # in plain-text mode; emphasis is intentionally dropped.
    body = {"chat_id": chat, "text": text}
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


async def notify_admin_error(
    *, settings: Settings, message: str, http_client: httpx.AsyncClient | None = None
) -> None:
    """Critical admin error — only fires if `Settings.notify_on_errors=True`."""
    if not settings.notify_on_errors:
        return
    url = svc()._discord_url()
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


# ── Per-scrape-run summary (plan 37 / 0.2.0.12) ────────────────────────


async def _send_discord_scrape_run(
    *,
    settings: Settings,
    run: JobScrapeRun,
    top_jobs: list[Job],
    http_client: httpx.AsyncClient | None = None,
) -> bool:
    """Post the per-scrape-run Discord embed. Silently no-ops when muted or
    webhook unset. Logs + returns False on transport error.
    """
    if not _is_event_enabled(settings, EVENT_SCRAPE_RUN_NEW_JOBS):
        return False
    url = svc()._discord_url()
    if not url:
        return False
    body = {"embeds": [_embed_for_scrape_run(run, top_jobs)]}
    client = http_client or httpx.AsyncClient(timeout=10.0)
    owns = http_client is None
    try:
        resp = await client.post(url, json=body)
        if resp.status_code >= 300:
            log.warning(
                "discord scrape-run webhook failed: %d %s",
                resp.status_code,
                resp.text[:200],
            )
            return False
        return True
    except httpx.RequestError as exc:
        log.warning("discord scrape-run webhook errored: %s", exc)
        return False
    finally:
        if owns:
            await client.aclose()


async def _send_telegram_scrape_run(
    *,
    settings: Settings,
    run: JobScrapeRun,
    top_jobs: list[Job],
    http_client: httpx.AsyncClient | None = None,
) -> bool:
    """Post the per-scrape-run Telegram summary. Silently no-ops when muted
    or bot token / chat id unset.
    """
    if not _is_event_enabled(settings, EVENT_SCRAPE_RUN_NEW_JOBS):
        return False
    token = svc()._telegram_token()
    chat = svc()._telegram_chat_id()
    if not token or not chat:
        return False
    text = _telegram_text_for_scrape_run(run, top_jobs)
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = {"chat_id": chat, "text": text}
    client = http_client or httpx.AsyncClient(timeout=10.0)
    owns = http_client is None
    try:
        resp = await client.post(url, json=body)
        if resp.status_code >= 300:
            log.warning(
                "telegram scrape-run send failed: %d %s",
                resp.status_code,
                resp.text[:200],
            )
            return False
        return True
    except httpx.RequestError as exc:
        log.warning("telegram scrape-run send errored: %s", exc)
        return False
    finally:
        if owns:
            await client.aclose()
