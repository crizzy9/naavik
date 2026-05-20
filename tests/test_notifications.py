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
    EVENT_SCRAPE_RUN_NEW_JOBS,
    _embed_for_event,
    _embed_for_scrape_run,
    _is_event_enabled,
    _telegram_text_for_event,
    _telegram_text_for_scrape_run,
    notify_application_submitted,
    notify_new_high_score,
    notify_scrape_run_summary,
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


# ── Per-scrape-run summary (plan 37 / 0.2.0.12) ─────────────────────────


def _scrape_run(**kw):
    """Plain-data JobScrapeRun stand-in. Real model is SQLModel-backed, but
    the notification builders only touch attributes — no ORM behavior needed.
    """
    from datetime import UTC, datetime

    from models import JobScrapeStatus, JobSource

    base = {
        "id": 901,
        "user_id": 1,
        "source": JobSource.LINKEDIN,
        "status": JobScrapeStatus.SUCCESS,
        "started_at": datetime(2026, 5, 19, 15, 0, tzinfo=UTC),
        "finished_at": datetime(2026, 5, 19, 15, 0, 1, tzinfo=UTC),
        "listings_returned": 12,
        "new_jobs": 5,
        "updated_jobs": 7,
        "errors": [],
        "duration_ms": 1400,
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _top_jobs(n: int) -> list:
    return [
        SimpleNamespace(
            id=100 + i,
            role=f"Senior Engineer {i}",
            company=f"Acme {i}",
            url=f"https://example.com/jobs/{100 + i}",
        )
        for i in range(n)
    ]


def test_event_scrape_run_default_on():
    """Empty notifications_enabled returns the on-by-default for the new event."""
    s = _settings()
    assert _is_event_enabled(s, EVENT_SCRAPE_RUN_NEW_JOBS) is True


def test_event_scrape_run_explicit_off():
    s = _settings(notifications_enabled={EVENT_SCRAPE_RUN_NEW_JOBS: False})
    assert _is_event_enabled(s, EVENT_SCRAPE_RUN_NEW_JOBS) is False


def test_embed_for_scrape_run_shape_and_color():
    run = _scrape_run(new_jobs=5, listings_returned=12, updated_jobs=7)
    embed = _embed_for_scrape_run(run, _top_jobs(5))
    assert "5 new jobs from linkedin" in embed["title"]
    # Cyan matches EVENT_NEW_HIGH_SCORE convention.
    assert embed["color"] == 5793266
    # Description carries each top job's link.
    for i in range(5):
        assert f"https://example.com/jobs/{100 + i}" in embed["description"]
    # No "+N more" line when the count fits exactly.
    assert "more" not in embed["description"]
    # Field block carries run summary + score-gate disclaimer.
    assert len(embed["fields"]) == 2
    assert "linkedin" in embed["fields"][0]["value"]
    assert "12 listings" in embed["fields"][0]["value"]
    assert "5 new" in embed["fields"][0]["value"]
    assert "0.3.0" in embed["fields"][1]["value"]


def test_embed_for_scrape_run_truncates_to_top_5_with_overflow_line():
    """50 new jobs → top-5 inline + a '+45 more' overflow line."""
    run = _scrape_run(new_jobs=50, listings_returned=60)
    embed = _embed_for_scrape_run(run, _top_jobs(50))
    # Only 5 links rendered + 1 overflow line.
    assert embed["description"].count("• ") == 6
    assert "+45 more" in embed["description"]


def test_telegram_text_for_scrape_run_under_4096_bytes():
    """5 long titles still fit comfortably under Telegram's 4096-byte limit."""
    run = _scrape_run(new_jobs=5, listings_returned=12, updated_jobs=7)
    fat_jobs = [
        SimpleNamespace(
            id=100 + i,
            role="S" * 200,  # 200-char role string
            company="C" * 200,
            url=f"https://example.com/jobs/{100 + i}",
        )
        for i in range(5)
    ]
    text = _telegram_text_for_scrape_run(run, fat_jobs)
    assert len(text.encode("utf-8")) < 4096
    assert "5 new jobs from linkedin" in text
    assert "_Run: 12 listings · 5 new · 7 updated · 1.4s_" in text


@pytest.mark.asyncio
async def test_notify_scrape_run_summary_no_op_when_no_new_jobs():
    """run.new_jobs == 0 → no Discord, no Telegram, no toast."""
    s = _settings()
    run = _scrape_run(new_jobs=0)
    discord = AsyncMock(return_value=False)
    tg = AsyncMock(return_value=False)
    while not notifications._TOAST_QUEUE.empty():
        notifications._TOAST_QUEUE.get_nowait()
    with (
        patch("services.notifications._send_discord_scrape_run", new=discord),
        patch("services.notifications._send_telegram_scrape_run", new=tg),
    ):
        await notify_scrape_run_summary(settings=s, run=run, top_jobs=[])
    discord.assert_not_awaited()
    tg.assert_not_awaited()
    assert notifications._TOAST_QUEUE.empty()


@pytest.mark.asyncio
async def test_notify_scrape_run_summary_fans_out_to_all_three_channels():
    """new_jobs > 0 → Discord + Telegram + toast all fire."""
    s = _settings()
    run = _scrape_run(new_jobs=5)
    while not notifications._TOAST_QUEUE.empty():
        notifications._TOAST_QUEUE.get_nowait()
    discord = AsyncMock(return_value=True)
    tg = AsyncMock(return_value=True)
    with (
        patch("services.notifications._send_discord_scrape_run", new=discord),
        patch("services.notifications._send_telegram_scrape_run", new=tg),
    ):
        await notify_scrape_run_summary(settings=s, run=run, top_jobs=_top_jobs(3))
    discord.assert_awaited_once()
    tg.assert_awaited_once()
    toast = notifications._TOAST_QUEUE.get_nowait()
    assert toast.kind == "info"
    assert "linkedin" in toast.title


@pytest.mark.asyncio
async def test_notify_scrape_run_summary_survives_one_channel_failure():
    """return_exceptions=True → a Discord raise doesn't cancel Telegram + toast."""
    s = _settings()
    run = _scrape_run(new_jobs=5)
    while not notifications._TOAST_QUEUE.empty():
        notifications._TOAST_QUEUE.get_nowait()

    async def _boom(**_kw):
        raise RuntimeError("discord exploded")

    tg = AsyncMock(return_value=True)
    with (
        patch("services.notifications._send_discord_scrape_run", new=_boom),
        patch("services.notifications._send_telegram_scrape_run", new=tg),
    ):
        # The whole gather must not raise.
        await notify_scrape_run_summary(settings=s, run=run, top_jobs=_top_jobs(3))
    tg.assert_awaited_once()
    # Toast still fires regardless.
    toast = notifications._TOAST_QUEUE.get_nowait()
    assert toast.kind == "info"


@pytest.mark.asyncio
async def test_send_discord_scrape_run_posts_embed():
    """Happy path: builds an embed and posts to the configured webhook."""
    from services.notifications import _send_discord_scrape_run

    s = _settings()
    run = _scrape_run(new_jobs=5)
    captured = {}
    client = _mock_client(captured)
    with patch(
        "services.notifications._discord_url",
        return_value="https://discord.example/webhook/scrape-run",
    ):
        ok = await _send_discord_scrape_run(
            settings=s, run=run, top_jobs=_top_jobs(5), http_client=client
        )
    await client.aclose()
    assert ok is True
    body = json.loads(captured["body"])
    assert body["embeds"][0]["title"].startswith("🆕 5 new jobs from linkedin")


@pytest.mark.asyncio
async def test_send_telegram_scrape_run_posts_plaintext():
    """Telegram outbound payload carries chat_id + NO parse_mode (markdown
    injection defense — scraper-controlled role/company/url could otherwise
    forge `[phish](url)` clickable links).
    """
    from services.notifications import _send_telegram_scrape_run

    s = _settings()
    run = _scrape_run(new_jobs=5)
    captured = {}
    client = _mock_client(captured)
    with (
        patch("services.notifications._telegram_token", return_value="bot-token"),
        patch("services.notifications._telegram_chat_id", return_value="42"),
    ):
        ok = await _send_telegram_scrape_run(
            settings=s, run=run, top_jobs=_top_jobs(3), http_client=client
        )
    await client.aclose()
    assert ok is True
    body = json.loads(captured["body"])
    assert body["chat_id"] == "42"
    assert "parse_mode" not in body
    assert "5 new jobs from linkedin" in body["text"]


@pytest.mark.asyncio
async def test_send_telegram_scrape_run_hostile_role_renders_as_plain_text():
    """A scraper-controlled `role` carrying Markdown link syntax
    `[phish](https://evil.example)` is sent verbatim, NOT as a clickable
    link — because no parse_mode is set, Telegram falls back to text
    rendering and the brackets/parens stay literal.
    """
    from services.notifications import _send_telegram_scrape_run

    hostile = [
        SimpleNamespace(
            id=999,
            role="[phish](https://evil.example)",
            company="*pretend-bold*",
            url="https://legit.example/jobs/999",
        )
    ]
    s = _settings()
    run = _scrape_run(new_jobs=1)
    captured = {}
    client = _mock_client(captured)
    with (
        patch("services.notifications._telegram_token", return_value="bot-token"),
        patch("services.notifications._telegram_chat_id", return_value="42"),
    ):
        ok = await _send_telegram_scrape_run(
            settings=s, run=run, top_jobs=hostile, http_client=client
        )
    await client.aclose()
    assert ok is True
    body = json.loads(captured["body"])
    # No parse_mode → Telegram won't interpret the bracket syntax as a link.
    assert "parse_mode" not in body
    # Hostile text is in the payload verbatim — defense is the absent
    # parse_mode, not sanitization.
    assert "[phish](https://evil.example)" in body["text"]
    assert "*pretend-bold*" in body["text"]
    assert "api.telegram.org/botbot-token/sendMessage" in captured["url"]
