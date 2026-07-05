"""Edge-triggered Discord alert when the Tier-B LinkedIn session dies (2026-07).

`scheduler.jobs._maybe_alert_linkedin_session` fires exactly once per
not-logged-in transition: the health file's `alerted` flag latches after the
first notification and a later "ok" recording re-arms it (latch behavior
itself is pinned in tests/test_linkedin_resolver.py).
"""

from __future__ import annotations

import os  # noqa: I001

os.environ.setdefault("NAAVIK_DEBUG", "1")

from contextlib import asynccontextmanager  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from unittest.mock import AsyncMock, MagicMock  # noqa: E402

import pytest  # noqa: E402


def _wire(monkeypatch, *, health, settings_row=...):
    from scheduler import jobs as sj
    from services import resolution as linkedin_resolver

    monkeypatch.setattr(linkedin_resolver, "read_session_health", lambda: health)
    latched: list[str] = []
    monkeypatch.setattr(linkedin_resolver, "mark_health_alerted", lambda: latched.append("x"))

    sent: list[str] = []

    async def _notify(*, settings, message, http_client=None):
        sent.append(message)

    monkeypatch.setattr("services.notify.notify_admin_error", _notify)

    if settings_row is ...:
        settings_row = SimpleNamespace(user_id=1, notify_on_errors=True)
    session = MagicMock()
    result = MagicMock()
    result.one_or_none = lambda: settings_row
    session.exec = AsyncMock(return_value=result)

    @asynccontextmanager
    async def _session_cm():
        yield session

    monkeypatch.setattr(sj, "async_session", _session_cm)
    return sj, sent, latched


@pytest.mark.asyncio
async def test_alert_fires_once_and_latches(monkeypatch):
    sj, sent, latched = _wire(monkeypatch, health={"status": "not_logged_in", "alerted": False})
    await sj._maybe_alert_linkedin_session()
    assert len(sent) == 1
    assert "linkedin_login.py" in sent[0]
    assert latched == ["x"]


@pytest.mark.asyncio
async def test_no_alert_when_already_latched(monkeypatch):
    sj, sent, latched = _wire(monkeypatch, health={"status": "not_logged_in", "alerted": True})
    await sj._maybe_alert_linkedin_session()
    assert sent == []
    assert latched == []


@pytest.mark.asyncio
@pytest.mark.parametrize("health", [None, {"status": "ok", "alerted": False}, {"status": "error"}])
async def test_no_alert_for_ok_error_or_missing_health(monkeypatch, health):
    sj, sent, latched = _wire(monkeypatch, health=health)
    await sj._maybe_alert_linkedin_session()
    assert sent == []
    assert latched == []
