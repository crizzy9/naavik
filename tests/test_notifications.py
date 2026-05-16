"""Wave 6 — notifications tests.

Per plan 10 § E. Coverage:
- Discord embed shape per event
- Telegram outbound shape per event
- Per-event toggle from Settings.notifications_enabled
- Toast queue is push/consume-safe
- High-score gate respects Settings.notify_threshold
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from services import notifications
from services.notifications import (
    EVENT_APPLICATION_SENT,
    EVENT_AUTO_APPLY_FAILED,
    EVENT_NEW_HIGH_SCORE,
    EVENT_REJECTION,
    _embed_for_event,
    _is_event_enabled,
    _telegram_text_for_event,
    notify_application_submitted,
    notify_new_high_score,
    push_toast,
    send_discord,
    send_telegram,
)

# ── Fakes ────────────────────────────────────────────────────────────


def _settings(**kw):
    base = {
        "notifications_enabled": None,
        "notify_threshold": 0.8,
        "notify_on_errors": True,
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _job(**kw):
    base = {
        "id": 1,
        "role": "Senior Backend Engineer",
        "company": "Stripe",
        "location": "Remote",
        "url": "https://example.com/jobs/1",
        "score": 0.92,
        "description": "Cool job",
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _application(**kw):
    from models import ApplicationBoard

    base = {
        "id": 1,
        "role": "Senior Backend Engineer",
        "company": "Stripe",
        "board": ApplicationBoard.GREENHOUSE,
        "submission_artifacts": None,
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _mock_client(captured: dict, response: httpx.Response | None = None):
    def _handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["body"] = req.read()
        return response or httpx.Response(204)

    return httpx.AsyncClient(transport=httpx.MockTransport(_handler))


# ── Embed shape ──────────────────────────────────────────────────────


def test_discord_embed_for_new_high_score():
    embed = _embed_for_event(EVENT_NEW_HIGH_SCORE, job=_job())
    assert "Stripe" in embed["title"]
    assert "0.92" in embed["fields"][0]["value"]


def test_discord_embed_for_application_sent():
    embed = _embed_for_event(EVENT_APPLICATION_SENT, application=_application())
    assert "Stripe" in embed["title"]
    assert embed["fields"][0]["value"] == "greenhouse"


def test_discord_embed_for_auto_apply_failed_includes_message():
    app = _application(
        submission_artifacts={
            "last_failure": {"kind": "auth_required", "message": "cookie expired"}
        }
    )
    embed = _embed_for_event(EVENT_AUTO_APPLY_FAILED, application=app)
    assert "cookie expired" in embed["description"]


def test_telegram_text_for_new_high_score_uses_markdown():
    text = _telegram_text_for_event(EVENT_NEW_HIGH_SCORE, job=_job())
    assert "*Stripe*" in text
    assert "0.92" in text
    assert "https://example.com/jobs/1" in text


# ── Per-event toggle ────────────────────────────────────────────────


def test_event_enabled_defaults():
    s = _settings()
    assert _is_event_enabled(s, EVENT_NEW_HIGH_SCORE) is True
    assert _is_event_enabled(s, EVENT_APPLICATION_SENT) is True
    # Rejections off by default — too noisy
    assert _is_event_enabled(s, EVENT_REJECTION) is False


def test_event_enabled_explicit_payload_overrides():
    s = _settings(notifications_enabled={EVENT_REJECTION: True, EVENT_NEW_HIGH_SCORE: False})
    assert _is_event_enabled(s, EVENT_REJECTION) is True
    assert _is_event_enabled(s, EVENT_NEW_HIGH_SCORE) is False


@pytest.mark.asyncio
async def test_send_discord_no_op_when_event_muted():
    s = _settings(notifications_enabled={EVENT_NEW_HIGH_SCORE: False})
    captured = {}
    client = _mock_client(captured)
    with patch("services.notifications._discord_url", return_value="https://discord/x"):
        ok = await send_discord(
            settings=s, event=EVENT_NEW_HIGH_SCORE, job=_job(), http_client=client
        )
    await client.aclose()
    assert ok is False
    assert captured == {}  # never called


@pytest.mark.asyncio
async def test_send_discord_no_op_without_webhook():
    s = _settings()
    with patch("services.notifications._discord_url", return_value=None):
        ok = await send_discord(settings=s, event=EVENT_NEW_HIGH_SCORE, job=_job())
    assert ok is False


@pytest.mark.asyncio
async def test_send_discord_posts_embed():
    s = _settings()
    captured = {}
    client = _mock_client(captured)
    with patch(
        "services.notifications._discord_url",
        return_value="https://discord.example/webhook",
    ):
        ok = await send_discord(
            settings=s, event=EVENT_APPLICATION_SENT, application=_application(), http_client=client
        )
    await client.aclose()
    assert ok is True
    body = json.loads(captured["body"])
    assert body["embeds"][0]["title"].startswith("Application submitted")


@pytest.mark.asyncio
async def test_send_telegram_no_op_without_token_or_chat():
    s = _settings()
    with (
        patch("services.notifications._telegram_token", return_value=None),
        patch("services.notifications._telegram_chat_id", return_value="42"),
    ):
        ok = await send_telegram(settings=s, event=EVENT_NEW_HIGH_SCORE, job=_job())
    assert ok is False


@pytest.mark.asyncio
async def test_send_telegram_posts_message():
    s = _settings()
    captured = {}
    client = _mock_client(captured)
    with (
        patch("services.notifications._telegram_token", return_value="bot-token"),
        patch("services.notifications._telegram_chat_id", return_value="42"),
    ):
        ok = await send_telegram(
            settings=s, event=EVENT_NEW_HIGH_SCORE, job=_job(), http_client=client
        )
    await client.aclose()
    assert ok is True
    body = json.loads(captured["body"])
    assert body["chat_id"] == "42"
    assert "Stripe" in body["text"]
    assert "api.telegram.org/botbot-token/sendMessage" in captured["url"]


# ── High-score gate ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_notify_new_high_score_skips_when_below_threshold():
    s = _settings(notify_threshold=0.95)
    job = _job(score=0.85)
    discord_called = False
    tg_called = False

    async def _fake_discord(*a, **kw):
        nonlocal discord_called
        discord_called = True
        return False

    async def _fake_tg(*a, **kw):
        nonlocal tg_called
        tg_called = True
        return False

    with (
        patch("services.notifications.send_discord", new=_fake_discord),
        patch("services.notifications.send_telegram", new=_fake_tg),
    ):
        await notify_new_high_score(settings=s, job=job)
    assert discord_called is False
    assert tg_called is False


@pytest.mark.asyncio
async def test_notify_new_high_score_dispatches_when_above_threshold():
    s = _settings(notify_threshold=0.5)
    job = _job(score=0.85)
    discord = AsyncMock(return_value=True)
    tg = AsyncMock(return_value=True)
    with (
        patch("services.notifications.send_discord", new=discord),
        patch("services.notifications.send_telegram", new=tg),
    ):
        await notify_new_high_score(settings=s, job=job)
    discord.assert_awaited()
    tg.assert_awaited()


# ── Toast queue ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_push_toast_enqueues_in_order():
    # Drain the queue first.
    while not notifications._TOAST_QUEUE.empty():
        notifications._TOAST_QUEUE.get_nowait()

    await push_toast("info", "first", "body1")
    await push_toast("warning", "second", "body2")
    assert notifications._TOAST_QUEUE.qsize() == 2
    a = notifications._TOAST_QUEUE.get_nowait()
    b = notifications._TOAST_QUEUE.get_nowait()
    assert a.title == "first"
    assert b.title == "second"
    assert a.kind == "info"
    assert b.kind == "warning"


@pytest.mark.asyncio
async def test_notify_application_submitted_pushes_toast():
    s = _settings()
    while not notifications._TOAST_QUEUE.empty():
        notifications._TOAST_QUEUE.get_nowait()
    with (
        patch("services.notifications.send_discord", new=AsyncMock(return_value=True)),
        patch("services.notifications.send_telegram", new=AsyncMock(return_value=True)),
    ):
        await notify_application_submitted(settings=s, application=_application())
    toast = notifications._TOAST_QUEUE.get_nowait()
    assert toast.kind == "success"
    assert "Stripe" in toast.body
